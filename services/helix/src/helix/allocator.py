"""HelixAllocator — Helios.md §11.4 second reference allocator.

Helix-lite v1 (`Helios.md §11.4` callout):

    Rank(s, user) = ReputationScore × CapacityFactor
                  × HelixFeeFactor(strategy_fee, user_max_fee, regime=NORMAL)
                  × ClassFitFactor

Differences from Sentinel's product (`§8.3`):

  • `HelixFeeFactor` is a continuous penalty in [0, 1] over the user's
    fee headroom, not a binary `fee ≤ max_fee` cutoff. Two strategies
    that both satisfy `max_fee_rate_bps` are not equally preferred —
    the cheaper one scores higher proportionally to remaining headroom.
  • Regime is pinned to `NORMAL` per §11.4 callout. Helix-v2 will read
    BTC realized vol via `helpers.market_data.btc_realized_vol_30d` and
    flip regime live; the rank function is structured to make that flip
    a one-line change.

`allocate` defers to the SDK's `score_weighted_allocation` over the
top-K-by-rank set. Correlation-aware greedy (`helix_greedy_pick`) is
NOT wired in v1 — it ships in the SDK helpers for third parties and
Helix-v2.

The whole point of Helix existing is to produce *different* decisions
than Sentinel on the same input. The fee-factor curvature is what
provides that divergence; if you change the curve, run
`services/helix/tests/test_allocator.py::test_diverges_from_sentinel`
to confirm divergence still holds on the demo fixture.
"""

from __future__ import annotations

from helios_allocator import BaseAllocator
from helios_allocator.helpers.regime import helix_fee_factor
from helios_allocator.types import AllocationTarget, MetaStrategy, Regime, StrategyCandidate

# Pin v1 regime per §11.4. Helix-v2 will swap this for a live read off
# `OraclePriceAnchor`-derived realized vol.
_HELIX_V1_REGIME: Regime = Regime.NORMAL


class HelixAllocator(BaseAllocator):
    name = "Helios Helix"
    fee_rate_bps = 600  # 6% — slightly higher than Sentinel's 4% per phase3-plan
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
        scores = self.rank_strategies(user, ranked)
        # Drop class-mismatch / fee-rejected / capacity-exhausted candidates so
        # they don't take a slot in `max_strategies_count`.
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
            * helix_fee_factor(c.fee_rate_bps, user.max_fee_rate_bps, _HELIX_V1_REGIME)
            * c.class_fit(user.allowed_strategy_classes)
        )
