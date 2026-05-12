"""StrategyAgent base class.

Subclass this to ship a strategy on the Helios marketplace. See
`Helios.md §10` for the full SDK contract.

Required override:
  * `on_bar(asset, snapshot)` — your signal logic.

Optional overrides (sensible defaults provided):
  * `size_trade(intent, available_capital)` — translate a trade
    intent into a notional USD amount. Default respects `intent`'s
    own sizing, capped by `max_position_size_usd` and the available
    capital.
  * `should_exit(asset, snapshot, position)` — supplemental exit
    hook the backtest engine consults each bar. Default returns
    `False`; the recommended pattern is still to express exits as
    `TradeIntent(direction=Direction.EXIT, ...)` from `on_bar`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import ClassVar

from helios.types import (
    Direction,
    MarketSnapshot,
    Position,
    RotationIntent,
    StrategyManifest,
    TradeIntent,
    YieldTick,
)


class StrategyAgent(ABC):
    """Subclass me. See `Helios.md §10`.

    Class-level configuration (override these on your subclass):
        declared_class: e.g. "momentum_v1"
        asset_universe: ["BTC", "ETH", "SOL", "BNB"]
        max_position_size_usd: hard cap per trade
        fee_rate_bps: 2_000 = 20% performance fee on realized profit
    """

    declared_class: ClassVar[str] = ""
    asset_universe: ClassVar[Sequence[str]] = ()
    max_position_size_usd: ClassVar[int] = 0
    fee_rate_bps: ClassVar[int] = 0

    def __init__(self) -> None:
        if not self.declared_class:
            raise RuntimeError(f"{type(self).__name__}.declared_class must be set on the subclass.")
        self._positions: dict[str, Position] = {}
        self._available_capital_usd: float = 0.0
        # Raw on-chain balance of the base asset (mUSDC) held by the
        # strategy's vault, in the asset's native units. Set alongside
        # `_available_capital_usd` by `seed_strategy_capital` so witness
        # builders can clamp `amount_in` to an integer the vault can
        # actually fund. Going through the USD float layer alone is
        # lossy: `int(raw/1e18 * 1e18)` can drift by a few thousand
        # wei (float64 ulp at ~4.5e19 is ~4096 wei), and
        # `safeTransferFrom` then reverts inside the swap, surfacing as
        # `TradeCallFailed(1)` from `StrategyVault`. `None` = unset.
        self._base_asset_balance_wei: int | None = None
        # PR4: track mark-to-market NAV alongside free cash so sizing
        # helpers can scale to the strategy's full footprint, not just
        # the unspent cash slice. The backtest engine refreshes this
        # before each bar; live runtimes call `_set_nav` after a fresh
        # `reportNAV` cycle. Defaults to cash so legacy code paths stay
        # correct on day-zero.
        self._nav_usd: float = 0.0
        # WS4: yield_rotation_v1 strategies track which market currently
        # holds capital so the SDK's yield-tick driver can attribute
        # realized APY between rotations. Directional classes never read
        # or write this field. `set_active_market` is the public setter
        # for runtimes that bridge a successful executeWithProof back to
        # the strategy's view of state.
        self._active_market: int | None = None

    # ── To be overridden by operators ────────────────────────
    @abstractmethod
    def on_bar(self, asset: str, snapshot: MarketSnapshot) -> TradeIntent | None:
        """Called for each asset on each bar close. Return a TradeIntent
        to trade, or None to do nothing."""
        ...

    def on_yield_tick(self, ticks: dict[int, YieldTick]) -> RotationIntent | None:
        """Called by the SDK's yield-tick driver for `yield_rotation_v1`
        strategies. `ticks` is the latest APY snapshot per allowlisted
        market. Return a `RotationIntent` to rotate, or `None` to hold.

        Default returns `None` — directional strategies never see this
        hook and do not need to override it. YR strategies must."""
        del ticks
        return None

    def size_trade(
        self,
        intent: TradeIntent,
        available_capital: float,
        *,
        nav_target: bool = False,
    ) -> float:
        """Translate a TradeIntent into a notional USD amount.

        Default policy: prefer the intent's own `amount_in_usd` when
        present; otherwise convert `amount_in_asset` using the price
        embedded in the snapshot if the strategy attached one
        (operators usually inline this in `on_bar`). Always clamps to
        `max_position_size_usd`. Headroom is `available_capital` by
        default; pass `nav_target=True` (or set
        `TradeIntent.is_nav_targeted=True`) to clamp against
        mark-to-market NAV instead — the right cap for "target X% of
        NAV per trade" sizing on a half-deployed strategy.

        Operators with custom sizing (Kelly, vol-target, …) override
        this and ignore the intent's `amount_in_usd`."""
        cap = float(self.max_position_size_usd) if self.max_position_size_usd else available_capital
        notional: float
        if intent.amount_in_usd is not None:
            notional = intent.amount_in_usd
        elif intent.amount_in_asset is not None:
            # Without a price the SDK cannot convert; surface zero so the
            # backtest engine treats the intent as a no-op rather than
            # silently mis-sizing.
            notional = 0.0
        else:
            notional = 0.0
        headroom = self._nav_usd if nav_target else available_capital
        return max(0.0, min(notional, cap, headroom))

    def should_exit(self, asset: str, snapshot: MarketSnapshot, position: Position) -> bool:
        """Supplemental exit hook the backtest engine consults each bar.

        Default returns `False`. The canonical pattern is to drive exits
        from `on_bar` by returning `TradeIntent(direction=Direction.EXIT,
        …)`; this hook exists for strategies that want a separate
        per-bar stop-loss or risk gate without polluting `on_bar`."""
        del asset, snapshot, position
        return False

    # ── Helpers available inside on_bar ──────────────────────
    @property
    def available_capital(self) -> float:
        return self._available_capital_usd

    @property
    def nav(self) -> float:
        """Mark-to-market NAV in USD: free cash + held positions valued
        at the latest tick. Use this (not `available_capital`) when
        sizing entries — a 90%-deployed strategy reads ~10% from
        `available_capital` but its real footprint is the full NAV."""
        return self._nav_usd

    def position_for(self, asset: str) -> float:
        pos = self._positions.get(asset)
        return pos.quantity if pos else 0.0

    def position_object(self, asset: str) -> Position | None:
        return self._positions.get(asset)

    @property
    def active_market(self) -> int | None:
        """The yield_rotation_v1 market currently holding capital, or
        None if the strategy is between rotations / has not deployed."""
        return self._active_market

    def set_active_market(self, market_id: int | None) -> None:
        """Used by `yield_rotation_v1` runtimes (and the SDK's yield
        backtest driver) to record a successful rotation. Strategies do
        not call this from `on_yield_tick`."""
        self._active_market = market_id

    def manifest(
        self, *, operator: str, stake_amount_usd: int, max_capacity_usd: int
    ) -> StrategyManifest:
        return StrategyManifest(
            declared_class=self.declared_class,
            asset_universe=self.asset_universe,
            max_capacity_usd=max_capacity_usd,
            fee_rate_bps=self.fee_rate_bps,
            operator=operator,
            stake_amount_usd=stake_amount_usd,
        )

    # ── Internal hooks the SDK uses (backtest, runtime) ──────
    def _set_capital(self, usd: float) -> None:
        self._available_capital_usd = usd

    def _set_nav(self, usd: float) -> None:
        self._nav_usd = usd

    def _set_base_asset_balance_wei(self, wei: int) -> None:
        """Record the exact integer balance the vault holds. Witness
        builders read this to clamp `amount_in` so `safeTransferFrom`
        cannot revert on a few-thousand-wei float roundtrip drift."""
        self._base_asset_balance_wei = wei

    def _set_position(
        self, asset: str, qty: float, avg_entry_price: float, direction: Direction
    ) -> None:
        if qty == 0:
            self._positions.pop(asset, None)
            return
        self._positions[asset] = Position(
            asset=asset, quantity=qty, avg_entry_price=avg_entry_price, direction=direction
        )
