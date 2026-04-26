"""The reference `MomentumStrategy`.

Implements the body of `Helios.md §10.2`'s minimal momentum example.
The runtime layer (oracle polling, prover round-trip, on-chain
submission) is in `runtime.py` — this module is just the strategy
operator's editable surface: the signal logic.

Class invariants enforced by `momentum_v1.circom`:
  * `asset_in`, `asset_out` ∈ manifest's asset universe
  * `amount_in ≤ max_position_size`
  * `min_amount_out` respects max slippage
  * Direction matches some threshold (LONG entry on N-period return >
    threshold; EXIT on signal flip; SHORT entry symmetric)
  * `block_window_end - block_window_start ≤ 100`

The strategy never reveals its `signal_threshold` — only that *some*
threshold exists for which the trade is consistent. That's the
operator's IP.
"""

from __future__ import annotations

from helios import Direction, MarketSnapshot, StrategyAgent, TradeIntent
from helios.types import Position


class MomentumStrategy(StrategyAgent):
    declared_class = "momentum_v1"
    asset_universe = ("USDC", "WKITE", "WETH")
    max_position_size_usd = 10_000
    fee_rate_bps = 2_000  # 20% of realized PnL above HWM

    def __init__(
        self,
        signal_threshold: float = 0.015,
        lookback_bars: int = 10,
        max_slippage_bps: int = 30,
        position_fraction: float = 0.5,
    ) -> None:
        super().__init__()
        # `signal_threshold` is private witness data — not serialized
        # alongside trades; only its existence is proven.
        self._signal_threshold = signal_threshold
        self._lookback = lookback_bars
        self._max_slippage_bps = max_slippage_bps
        self._position_fraction = position_fraction

    # ── Operator surface ───────────────────────────────────────
    def on_bar(self, asset: str, snapshot: MarketSnapshot) -> TradeIntent | None:
        if asset == "USDC":
            return None  # base asset — never the signal subject
        recent_return = snapshot.return_over(bars=self._lookback)
        position = self.position_for(asset)

        # Long entry: positive momentum + flat-or-short.
        if recent_return > self._signal_threshold and position <= 0:
            return TradeIntent(
                asset_in="USDC",
                asset_out=asset,
                amount_in_usd=self._size(),
                direction=Direction.LONG,
                max_slippage_bps=self._max_slippage_bps,
            )

        # Exit: signal flip while we still hold long.
        if recent_return < -self._signal_threshold and position > 0:
            return TradeIntent(
                asset_in=asset,
                asset_out="USDC",
                amount_in_asset=position,
                direction=Direction.EXIT,
                max_slippage_bps=self._max_slippage_bps,
            )

        return None

    # ── Internal sizing ───────────────────────────────────────
    def _size(self) -> float:
        return min(
            float(self.max_position_size_usd),
            self.available_capital * self._position_fraction,
        )

    # ── Test/runtime helpers ──────────────────────────────────
    def set_capital(self, usd: float) -> None:
        self._available_capital_usd = usd

    def set_position(self, asset: str, qty: float, avg_price: float, direction: Direction) -> None:
        self._positions[asset] = Position(
            asset=asset, quantity=qty, avg_entry_price=avg_price, direction=direction
        )

    @property
    def signal_threshold(self) -> float:
        """Exposed for the witness builder — never log/serialize this."""
        return self._signal_threshold

    @property
    def lookback_bars(self) -> int:
        return self._lookback
