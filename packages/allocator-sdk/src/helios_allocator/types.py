"""Public types for the allocator SDK."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, Field


class Regime(StrEnum):
    LOW_VOL = "low_vol"
    NORMAL = "normal"
    HIGH_VOL = "high_vol"


class MetaStrategy(BaseModel):
    """The user's signed allocation policy. Mirrors the on-chain MetaStrategy struct."""

    user_address: str
    allowed_strategy_classes: Sequence[str]
    allowed_assets: Sequence[str]
    allowed_chains: Sequence[int]
    max_capital_usd: int
    max_per_strategy_bps: int
    max_strategies_count: int
    drawdown_threshold_bps: int
    max_fee_rate_bps: int
    rebalance_cadence_sec: int
    valid_until: int  # unix timestamp
    # WS7.B reputation cold-start (`Helios.md §8.7`). `bootstrap_share_bps` of
    # total capital is reserved for strategies with `trades_attested <
    # min_attested_trades`; the rest follows the allocator's main rank function.
    # Defaults match `docs/phase2-plan.md §WS7.B` (10% bootstrap, 50 trades to
    # graduate).
    bootstrap_share_bps: int = 1000
    min_attested_trades: int = 50


class StrategyCandidate(BaseModel):
    """An allocator's view of a strategy. Populated from Goldsky + ReputationAnchor."""

    strategy_id: str  # contract address
    declared_class: str
    chain_id: int
    operator: str
    fee_rate_bps: int
    stake_amount_usd: int
    max_capacity_usd: int
    current_allocations_usd: int = 0

    reputation_score: float = 0.0
    realized_volatility_30d: float = 0.0
    sharpe_30d: float = 0.0
    max_drawdown_30d_bps: int = 0
    # Lifetime attested-trade count from the strategy registry / subgraph.
    # WS7.B uses this to gate the bootstrap pool: strategies under
    # `MetaStrategy.min_attested_trades` are eligible for cold-start capital.
    trades_attested: int = 0

    def capacity_factor(self) -> float:
        if self.max_capacity_usd <= 0:
            return 0.0
        return max(0.0, 1.0 - (self.current_allocations_usd / self.max_capacity_usd))

    def fee_fit(self, max_fee_rate_bps: int) -> float:
        return 1.0 if self.fee_rate_bps <= max_fee_rate_bps else 0.0

    def class_fit(self, allowed_classes: Sequence[str]) -> float:
        return 1.0 if self.declared_class in allowed_classes else 0.0


class AllocationTarget(BaseModel):
    """Concrete capital target the allocator will deploy."""

    strategy_id: str
    chain_id: int
    capital_usd: int = Field(ge=0)
    weight_bps: int = Field(ge=0, le=10_000)
