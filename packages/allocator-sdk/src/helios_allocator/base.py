"""BaseAllocator — the contract every allocator subclass implements.

Phase 0 ships the abstract surface so service code can import it. Phase 3
backfills the concrete behavior:
  - User onboarding (accepting signed meta-strategies, validating constraints)
  - Drawdown monitoring at 60s cadence
  - Fee crystallization at HWM thresholds
  - Defund + rebalance tx submission via Kite Passport sessions
  - Goldsky integration for strategy discovery + reputation reads
  - ReputationAnchor integration for the allocator's own reputation
  - WebSocket event emission
  - Stake management
  - Local backtest harness
  - Docker packaging
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import ClassVar

from helios_allocator.types import AllocationTarget, MetaStrategy, StrategyCandidate


class BaseAllocator(ABC):
    """Subclass me. See Helios.md §11.

    Class-level config (override on subclass):
        name: human-readable name. "Helios Sentinel" / "Helios Helix" reserved.
        fee_rate_bps: 500 = 5% of net realized profit above HWM
        supported_classes: which strategy classes this allocator will allocate to
    """

    name: ClassVar[str] = ""
    fee_rate_bps: ClassVar[int] = 0
    supported_classes: ClassVar[Sequence[str]] = ()

    # ── To be implemented by allocator authors ───────────────
    @abstractmethod
    def rank_strategies(
        self,
        user: MetaStrategy,
        candidates: list[StrategyCandidate],
    ) -> list[float]:
        """Return one score per candidate. Higher is better."""
        ...

    @abstractmethod
    def allocate(
        self,
        user: MetaStrategy,
        ranked: list[StrategyCandidate],
        capital: int,
    ) -> list[AllocationTarget]:
        """Convert a ranked list (best → worst) into concrete allocation targets."""
        ...

    # ── Default helpers (use in your `allocate` method) ──────
    def default_top_k_allocation(
        self,
        user: MetaStrategy,
        ranked: list[StrategyCandidate],
        capital: int,
    ) -> list[AllocationTarget]:
        """Take the top-K candidates and split capital evenly, capped per-strategy."""
        k = min(user.max_strategies_count, len(ranked))
        if k == 0 or capital == 0:
            return []
        per_strategy_cap = (capital * user.max_per_strategy_bps) // 10_000
        per_each = min(per_strategy_cap, capital // k)
        weight_bps = (per_each * 10_000) // capital if capital else 0
        return [
            AllocationTarget(
                strategy_id=c.strategy_id,
                chain_id=c.chain_id,
                capital_usd=per_each,
                weight_bps=weight_bps,
            )
            for c in ranked[:k]
        ]

    def score_weighted_allocation(
        self,
        user: MetaStrategy,
        selected: list[StrategyCandidate],
        capital: int,
        scores: list[float] | None = None,
    ) -> list[AllocationTarget]:
        """Weight selected candidates by their score. Caps each at max_per_strategy_bps."""
        if not selected or capital == 0:
            return []
        if scores is None:
            scores = self.rank_strategies(user, selected)
        total = sum(max(0.0, s) for s in scores)
        if total <= 0:
            return self.default_top_k_allocation(user, selected, capital)
        cap = (capital * user.max_per_strategy_bps) // 10_000
        results: list[AllocationTarget] = []
        for c, s in zip(selected, scores, strict=True):
            share = max(0.0, s) / total
            amount = min(int(capital * share), cap)
            weight_bps = (amount * 10_000) // capital if capital else 0
            results.append(
                AllocationTarget(
                    strategy_id=c.strategy_id,
                    chain_id=c.chain_id,
                    capital_usd=amount,
                    weight_bps=weight_bps,
                )
            )
        return results
