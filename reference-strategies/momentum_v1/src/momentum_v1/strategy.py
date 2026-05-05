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
                is_signal_flip=True,
            )

        return None

    # ── Internal sizing ───────────────────────────────────────
    def _size(self) -> float:
        # PR4: scale entries against current NAV (cash + mark-to-market
        # of held positions) — the prior `available_capital`-only sizing
        # collapsed to a tiny slice of the real footprint once the
        # strategy was already deployed. `size_trade` still clamps the
        # result to free cash so we never spend what we don't have.
        return min(
            float(self.max_position_size_usd),
            self.nav * self._position_fraction,
        )

    # ── Test/runtime helpers ──────────────────────────────────
    # `set_capital` / `set_position` delegate to the SDK base hooks. They
    # exist as public test-harness aliases so tests can seed state without
    # importing the underscore-prefixed internals; they don't add new
    # behaviour beyond resetting NAV alongside capital (a fresh allocation
    # has no holdings, so cash == NAV).
    def set_capital(self, usd: float) -> None:
        self._set_capital(usd)
        self._set_nav(usd)

    def set_position(self, asset: str, qty: float, avg_price: float, direction: Direction) -> None:
        self._set_position(asset, qty, avg_price, direction)

    @property
    def signal_threshold(self) -> float:
        """Exposed for the witness builder — never log/serialize this."""
        return self._signal_threshold

    @property
    def lookback_bars(self) -> int:
        return self._lookback
