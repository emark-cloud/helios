"""Public types exposed to strategy operators."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum

from pydantic import BaseModel, Field


class Direction(IntEnum):
    """Trade direction. Mirrors the on-chain enum in StrategyVault."""

    EXIT = 0
    LONG = 1
    SHORT = 2


class TradeIntent(BaseModel):
    """A strategy's intent to place a trade. The SDK turns this into calldata + proof."""

    asset_in: str
    asset_out: str
    direction: Direction
    amount_in_usd: float | None = None
    amount_in_asset: float | None = None
    max_slippage_bps: int = 50
    block_window_bars: int = 5
    # PR4: mean-reversion exits must specify *which* gate fired so the
    # circuit's `is_exit === is_signal_flip + is_stop_loss` constraint
    # is satisfied. The earlier shape carried these as instance flags
    # on `MeanReversionStrategy`, which raced across assets when the
    # runtime's `tick_bar` reset them between `on_bar` calls. Carrying
    # them on the intent itself makes them per-trade and immutable.
    # Both default False; set them ONLY on EXIT intents and never both.
    is_signal_flip: bool = False
    is_stop_loss: bool = False
    # WS4 PR 3/3: signals that `amount_in_usd` was computed against
    # mark-to-market NAV (via `helios.sizing.nav_target_notional`) and
    # should be allowed to clear the strategy's `available_capital`
    # cap. The engine's `size_trade` path still clamps a NAV-targeted
    # notional to `nav` and the `_apply_intent` down-size guard still
    # fits the trade to actual free cash on a half-deployed strategy
    # — this flag only widens the sizing band, it doesn't bypass cash.
    is_nav_targeted: bool = False

    def model_post_init(self, _ctx: object) -> None:
        if self.amount_in_usd is None and self.amount_in_asset is None:
            raise ValueError("Provide amount_in_usd or amount_in_asset.")
        if (self.is_signal_flip or self.is_stop_loss) and self.direction != Direction.EXIT:
            raise ValueError("is_signal_flip / is_stop_loss are EXIT-only flags")
        if self.is_signal_flip and self.is_stop_loss:
            raise ValueError("is_signal_flip and is_stop_loss are mutually exclusive")


class Position(BaseModel):
    asset: str
    quantity: float
    avg_entry_price: float
    direction: Direction


class MarketSnapshot(BaseModel):
    """Snapshot the SDK passes to `on_bar`. Contains recent prices for one asset."""

    asset: str
    timestamp: datetime
    prices: list[float] = Field(description="Recent close prices, oldest → newest")
    bar_interval_sec: int = 60

    def return_over(self, bars: int) -> float:
        if len(self.prices) < bars + 1:
            return 0.0
        old = self.prices[-(bars + 1)]
        new = self.prices[-1]
        if old == 0:
            return 0.0
        return (new - old) / old


class StrategyManifest(BaseModel):
    """Mirrors the on-chain manifest. The SDK derives this from the StrategyAgent subclass."""

    declared_class: str
    asset_universe: Sequence[str]
    max_capacity_usd: int
    fee_rate_bps: int
    operator: str
    stake_amount_usd: int
    # Poseidon commitment to the operator-declared circuit parameters
    # (max_position_size, max_slippage_bps, signal_threshold, stop_loss_price).
    # The on-chain StrategyVault asserts this against the params_hash public
    # input on every executeWithProof — so the prover cannot lie about the
    # declared bounds. Phase 1 deploy script defaults to bytes32(0); real
    # strategies must compute and supply this before registering.
    params_hash: str = "0x" + "0" * 64


# ── yield_rotation_v1: yield-driven hooks ───────────────────────────
#
# YR strategies fire on yield-oracle ticks rather than per-bar prices, so
# the SDK ships a separate intent + tick type. The driver in
# `helios.backtest.run_yield_backtest` wires these into the runtime
# loop the way the bar engine wires `on_bar` + `TradeIntent`.


@dataclass(frozen=True, slots=True)
class YieldTick:
    """A single APY observation for a market.

    Mirrors `oracle.yield_state.YieldSnapshot` minus the signature bytes
    — strategies don't verify oracle signatures locally; that's the
    on-chain anchor's job.
    """

    market_id: int
    """Stable, registry-assigned market identifier (uint64). Both the
    yield Merkle tree and the operator allowlist key on this id."""

    apy_bps_e6: int
    """APY in basis-points × 1e6 (so 5.25% APY = 525_000_000)."""

    timestamp_ms: int


@dataclass(frozen=True, slots=True)
class RotationIntent:
    """The operator's intent to rotate capital between two markets.

    Distinct from `TradeIntent` because the field set is different:
    no asset-in/out, no slippage, no direction enum. The witness
    builder turns this into a YR-circuit-shaped payload.

    Phase-3 review MEDIUM: `amount_in_usd` accepts `int | float` for
    operator ergonomics (callers like `self._size()` may already work
    in floats), but is normalized to `int` USD-cents-of-precision in
    `__post_init__`. The downstream witness builder converts to e18
    via `int(value * 10**18)`, and float64 only carries ~15-16 decimal
    digits — values above ~9.0e6 USD lose integer precision in the e18
    result. Storing the canonical value as `int` lets the prover
    handle USD-magnitudes far above that ceiling without silent
    rounding."""

    m_from: int
    m_to: int
    # `int | float` accepted at the public boundary so operator code
    # (`self._size()`, backtest fixtures) doesn't have to wrap with
    # `int(...)`. `__post_init__` normalizes to `int` so the downstream
    # witness builder's `int(value * 10**18)` never sees a float.
    amount_in_usd: int | float
    apy_from_bps: int
    apy_to_bps: int

    def __post_init__(self) -> None:
        if self.m_from == self.m_to:
            raise ValueError("rotation must change markets")
        # Coerce float ergonomics into the canonical int. Use
        # object.__setattr__ because the dataclass is frozen.
        if isinstance(self.amount_in_usd, float):
            object.__setattr__(self, "amount_in_usd", int(self.amount_in_usd))
        if self.amount_in_usd <= 0:
            raise ValueError("amount_in_usd must be positive")
