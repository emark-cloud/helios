"""Sentinel's `BaseAllocator` implementation.

The Phase-1 allocator is the legible reference baseline (`Helios.md
§8.3` + §11.2). Ranking is the canonical product:

    Rank(s, user) = ReputationScore × CapacityFactor × FeeFactor × ClassFitFactor

`allocate` defers to the SDK's `score_weighted_allocation` helper to
distribute capital proportional to rank, capped per-strategy by the
user's `max_per_strategy_bps`.

WS7.B splits `allocate` into a main pool and a reputation-cold-start
bootstrap pool (`Helios.md §8.7`). `user.bootstrap_share_bps` of total
capital is reserved for strategies with `trades_attested <
user.min_attested_trades`, allocated stake-weighted with a flat
performance prior. The main pool keeps the existing rank product over
the remaining capital. Both pools' outputs are merged per strategy and
re-capped at `max_per_strategy_bps` so a strategy that wins both pools
does not exceed the user's stated risk envelope.

The point of Sentinel is *not* to be sophisticated — Helix and any
third-party allocator will compete to outperform it. Sentinel proves
the marketplace mechanism end-to-end with the simplest possible math.
"""

from __future__ import annotations

from collections.abc import Sequence

from helios_allocator import BaseAllocator
from helios_allocator.types import AllocationTarget, MetaStrategy, StrategyCandidate


class SentinelAllocator(BaseAllocator):
    name = "Helios Sentinel"
    fee_rate_bps = 400  # 4% — phase1-plan.md §"Setup", confirmed 2026-04-25
    supported_classes = ("momentum_v1", "mean_reversion_v1", "yield_rotation_v1")

    def rank_strategies(
        self,
        user: MetaStrategy,
        candidates: list[StrategyCandidate],
    ) -> list[float]:
        return [self._score(c, user) for c in candidates]

    def allocate(
        self,
        user: MetaStrategy,
        ranked: list[StrategyCandidate],
        capital: int,
    ) -> list[AllocationTarget]:
        if capital <= 0 or not ranked:
            return []

        bootstrap_capital, main_capital = _split_capital(capital, user.bootstrap_share_bps)
        bootstrap_targets = self._allocate_bootstrap(user, ranked, bootstrap_capital)
        # If no cold-start strategy is eligible, the bootstrap budget falls back
        # to the main pool — otherwise a user with `bootstrap_share_bps > 0`
        # but a fully-graduated cohort would leave 10% of capital idle.
        deployed_bootstrap = sum(t.capital_usd for t in bootstrap_targets)
        main_capital += bootstrap_capital - deployed_bootstrap

        main_targets = self._allocate_main(user, ranked, main_capital)

        return _merge_targets(
            main_targets,
            bootstrap_targets,
            total_capital=capital,
            max_per_strategy_bps=user.max_per_strategy_bps,
        )

    # ── Main pool: classic rank product over remaining capital ──
    def _allocate_main(
        self,
        user: MetaStrategy,
        ranked: list[StrategyCandidate],
        capital: int,
    ) -> list[AllocationTarget]:
        if capital <= 0:
            return []
        scores = self.rank_strategies(user, ranked)
        # Strategies whose score collapsed to 0 (class-mismatch / fee /
        # capacity exhausted) are filtered out so they don't take up a
        # slot in `max_strategies_count`.
        eligible = [(c, s) for c, s in zip(ranked, scores, strict=True) if s > 0]
        eligible = eligible[: user.max_strategies_count]
        if not eligible:
            return []
        candidates = [c for c, _ in eligible]
        sub_scores = [s for _, s in eligible]
        return self.score_weighted_allocation(user, candidates, capital, scores=sub_scores)

    # ── Bootstrap pool (WS7.B / Helios.md §8.7) ─────────────────
    def _allocate_bootstrap(
        self,
        user: MetaStrategy,
        ranked: list[StrategyCandidate],
        capital: int,
    ) -> list[AllocationTarget]:
        if capital <= 0 or user.min_attested_trades <= 0:
            return []
        # Cold-start eligibility: declared class + fee fit (user's hard
        # constraints) AND the trades_attested gate. We deliberately do
        # *not* require non-zero reputation here — that's what the
        # bootstrap pool is for. Capacity factor still applies so a
        # full-capacity strategy isn't oversubscribed.
        eligible = [
            c
            for c in ranked
            if c.trades_attested < user.min_attested_trades
            and c.class_fit(user.allowed_strategy_classes) > 0
            and c.fee_fit(user.max_fee_rate_bps) > 0
            and c.capacity_factor() > 0
        ]
        if not eligible:
            return []
        # Flat performance prior → stake-weighted only. Strategies that
        # over-collateralize signal more skin in the game, which is the
        # only legible signal we have before any trades land.
        stakes = [float(max(0, c.stake_amount_usd)) for c in eligible]
        if sum(stakes) <= 0:
            # No staked candidates — fall back to even split so a
            # bootstrap-share-bps configured user still funnels capital.
            return self.default_top_k_allocation(user, eligible, capital)
        return self.score_weighted_allocation(user, eligible, capital, scores=stakes)

    def _score(self, c: StrategyCandidate, user: MetaStrategy) -> float:
        return (
            c.reputation_score
            * c.capacity_factor()
            * c.fee_fit(user.max_fee_rate_bps)
            * c.class_fit(user.allowed_strategy_classes)
        )


def _split_capital(capital: int, bootstrap_share_bps: int) -> tuple[int, int]:
    """Return (bootstrap, main) capital. Bootstrap rounds down so the main
    pool absorbs the remainder."""
    if bootstrap_share_bps <= 0:
        return 0, capital
    bps = min(10_000, bootstrap_share_bps)
    bootstrap = capital * bps // 10_000
    return bootstrap, capital - bootstrap


def _merge_targets(
    main: Sequence[AllocationTarget],
    bootstrap: Sequence[AllocationTarget],
    *,
    total_capital: int,
    max_per_strategy_bps: int,
) -> list[AllocationTarget]:
    """Merge per-strategy capital across pools and cap at the user's
    `max_per_strategy_bps`. Re-derives `weight_bps` against the total
    capital so the dashboard reports a single coherent split.
    """
    if total_capital <= 0:
        return []
    cap = (total_capital * max_per_strategy_bps) // 10_000

    by_id: dict[str, AllocationTarget] = {}
    for t in (*main, *bootstrap):
        existing = by_id.get(t.strategy_id)
        if existing is None:
            by_id[t.strategy_id] = t
            continue
        # Same strategy showed up in both pools — sum capital, then re-cap.
        merged_capital = min(cap, existing.capital_usd + t.capital_usd)
        by_id[t.strategy_id] = AllocationTarget(
            strategy_id=t.strategy_id,
            chain_id=t.chain_id,
            capital_usd=merged_capital,
            weight_bps=(merged_capital * 10_000) // total_capital,
        )

    # Re-cap any single-pool target that still exceeds the per-strategy cap
    # after rounding (defensive — score_weighted_allocation already caps).
    # Also re-derives weight_bps against the user's full delegation so the
    # dashboard reports a coherent split (sub-pool calls divide by their
    # own capital, not the total).
    out: list[AllocationTarget] = []
    for original in by_id.values():
        capped_capital = min(original.capital_usd, cap)
        out.append(
            AllocationTarget(
                strategy_id=original.strategy_id,
                chain_id=original.chain_id,
                capital_usd=capped_capital,
                weight_bps=(capped_capital * 10_000) // total_capital,
            )
        )
    return out


def diff_allocations(
    current_capital: dict[str, int],
    target: Sequence[AllocationTarget],
) -> list[tuple[str, int]]:
    """Return (strategy, delta) ops needed to move from current to target.

    Positive delta → ADD or INCREASE (`allocateToStrategy(amount=delta)`).
    Negative delta → DECREASE (encoded via `rebalance` weight reduction
    or `defundStrategy` for full removal). Zero deltas are dropped.

    The caller (decision loop) decides whether each op becomes a
    discrete `allocateToStrategy` call or a single `rebalance` batch
    based on `user.rebalance_cadence_sec`.
    """
    ops: list[tuple[str, int]] = []
    seen: set[str] = set()
    for t in target:
        seen.add(t.strategy_id)
        delta = t.capital_usd - current_capital.get(t.strategy_id, 0)
        if delta != 0:
            ops.append((t.strategy_id, delta))
    for sid, deployed in current_capital.items():
        if sid in seen or deployed == 0:
            continue
        ops.append((sid, -deployed))  # full removal
    return ops
