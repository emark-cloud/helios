"""Pydantic models exposed at every allocator service's REST/WS boundary.

The on-chain `MetaStrategyLib.MetaStrategy` and the SDK's `MetaStrategy`
are isomorphic — these schemas accept a JSON payload from the frontend /
SDK consumer, then `to_sdk_meta()` projects into the SDK shape used by
allocator implementations' `rank_strategies` / `allocate`.

Phase 4 (WS-FE-1) introduces the `auth` enum on the payload:

  * `"passport"` — the user signed a batched userOp via Kite Passport
    that already landed `UserVault.setMetaStrategy` on chain. The
    signature field is `0x`; the server only enforces the
    `(user, nonce)` / `valid_until` replay window.
  * `"eip191"` — wagmi `personal_sign` over the canonical JSON digest
    (anvil/dev path). The server verifies the EIP-191 signature plus
    the same replay window.

Phase 5 will replace the EIP-191 path with EIP-1271 verification
against the AA wallet on chain; the wire shape stays the same.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, Field

from helios_allocator.types import MetaStrategy as SDKMetaStrategy

AuthMode = Literal["passport", "eip191"]


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
    # Replay protection: a fresh 64-bit nonce minted by the frontend per
    # signing attempt. The server records (user_address, nonce) and
    # rejects duplicates within the `valid_until` window. Without this
    # field a captured signature could be re-submitted indefinitely up
    # to its `valid_until`, re-binding a delegation the user revoked.
    nonce: int = Field(ge=0, lt=2**64)
    # WS7.B reputation cold-start (`Helios.md §8.7`). Defaults match
    # `docs/phase4-plan.md §WS7.B` and the on-chain meta-strategy spec.
    bootstrap_share_bps: int = Field(default=1000, ge=0, le=10_000)
    min_attested_trades: int = Field(default=50, ge=0)
    # EIP-191 signature for the legacy / dev path. Empty (`"0x"`) for
    # Passport-onboarded users — the userOp at the EntryPoint is the
    # user's authorization in that mode.
    signature: str = Field(default="0x")
    auth: AuthMode = Field(default="eip191")

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
    # Phase-3 review MEDIUM: these were previously hardcoded to 0/0.0 in
    # both Sentinel and Helix because neither service joins the
    # reputation-engine snapshot into the directory row. Marked optional
    # so callers serialize `None` (omitted from JSON when callers use
    # `exclude_none=True`) rather than misleading zeros. Phase 4 wires
    # these up through the engine's `/v1/audit/{actor}` cache.
    realized_volatility_30d: float | None = None
    sharpe_30d: float | None = None
    max_drawdown_30d_bps: int | None = None
