"""Sentinel's `BaseAllocator` implementation.

The Phase-1 allocator is the legible reference baseline (`Helios.md
§8.3` + §11.2). Ranking is the canonical product:

    Rank(s, user) = ReputationScore × CapacityFactor × FeeFactor × ClassFitFactor

`allocate` defers to the SDK's `score_weighted_allocation` helper to
distribute capital proportional to rank, capped per-strategy by the
user's `max_per_strategy_bps`.

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
        # `ranked` arrives best-first from the loop; SDK helper computes
        # weights from rank scores and caps each at `max_per_strategy_bps`.
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

    def _score(self, c: StrategyCandidate, user: MetaStrategy) -> float:
        return (
            c.reputation_score
            * c.capacity_factor()
            * c.fee_fit(user.max_fee_rate_bps)
            * c.class_fit(user.allowed_strategy_classes)
        )


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
