"""Pydantic models exposed at every allocator service's REST/WS boundary.

The on-chain `MetaStrategyLib.MetaStrategy` and the SDK's `MetaStrategy`
are isomorphic — these schemas accept a JSON payload from the frontend /
SDK consumer, then `to_sdk_meta()` projects into the SDK shape used by
allocator implementations' `rank_strategies` / `allocate`.

`[PASSPORT-STUB]` — the `signature` field is recorded for forward
compatibility with Kite Passport; Phase 1 verifies an EOA `personal_sign`
over a canonical digest (`auth.py`). Phase 4 swaps in AA userOp
verification.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, Field

from helios_allocator.types import MetaStrategy as SDKMetaStrategy


class MetaStrategyPayload(BaseModel):
    """JSON shape accepted by `POST /v1/users/{user}/meta-strategy`."""

    user_address: str
    allowed_strategy_classes: Sequence[str] = Field(default_factory=list)
    allowed_assets: Sequence[str] = Field(default_factory=list)
    allowed_chains: Sequence[int] = Field(default_factory=list)
    max_capital_usd: int = Field(ge=0)
    max_per_strategy_bps: int = Field(ge=0, le=10_000)
    max_strategies_count: int = Field(ge=1, le=20)
    drawdown_threshold_bps: int = Field(ge=0, le=10_000)
    max_fee_rate_bps: int = Field(ge=0, le=10_000)
    rebalance_cadence_sec: int = Field(ge=60)
    valid_until: int = Field(ge=0)
    # WS7.B reputation cold-start (`Helios.md §8.7`). Defaults match
    # `docs/phase2-plan.md §WS7.B` and the on-chain meta-strategy spec.
    bootstrap_share_bps: int = Field(default=1000, ge=0, le=10_000)
    min_attested_trades: int = Field(default=50, ge=0)
    signature: str = Field(default="0x")  # [PASSPORT-STUB]

    def to_sdk_meta(self) -> SDKMetaStrategy:
        return SDKMetaStrategy(
            user_address=self.user_address,
            allowed_strategy_classes=list(self.allowed_strategy_classes),
            allowed_assets=list(self.allowed_assets),
            allowed_chains=list(self.allowed_chains),
            max_capital_usd=self.max_capital_usd,
            max_per_strategy_bps=self.max_per_strategy_bps,
            max_strategies_count=self.max_strategies_count,
            drawdown_threshold_bps=self.drawdown_threshold_bps,
            max_fee_rate_bps=self.max_fee_rate_bps,
            rebalance_cadence_sec=self.rebalance_cadence_sec,
            valid_until=self.valid_until,
            bootstrap_share_bps=self.bootstrap_share_bps,
            min_attested_trades=self.min_attested_trades,
        )


class AllocationView(BaseModel):
    """One row in the user's dashboard allocations table."""

    strategy_id: str
    chain_id: int
    declared_class: str
    capital_deployed_usd: int
    high_water_mark_usd: int
    current_nav_usd: int
    drawdown_bps: int
    defunded: bool = False
    last_rebalance_ts: int = 0


class DashboardPayload(BaseModel):
    user_address: str
    total_capital_usd: int
    total_nav_usd: int
    realized_pnl_usd: int
    fees_paid_usd: int
    allocations: list[AllocationView]
    allocator_name: str
    allocator_fee_rate_bps: int


class StrategyDirectoryRow(BaseModel):
    strategy_id: str
    declared_class: str
    chain_id: int
    operator: str
    fee_rate_bps: int
    stake_amount_usd: int
    max_capacity_usd: int
    current_allocations_usd: int
    reputation_score: float
    realized_volatility_30d: float
    sharpe_30d: float
    max_drawdown_30d_bps: int
