"""The reference `MeanReversionStrategy`.

Implements the body of `Helios.md §10.3`'s minimal mean-reversion
example. The runtime layer (oracle polling, prover round-trip, on-chain
submission) is in `runtime.py` — this module is just the strategy
operator's editable surface: the signal logic.

Class invariants enforced by `mean_reversion_v1.circom`:
  * `asset_in`, `asset_out` ∈ manifest's asset universe
  * `amount_in ≤ max_position_size`
  * `min_amount_out` respects max slippage
  * Direction matches *some* operator-declared n-sigma threshold:
    - LONG entry on N-sigma DOWN (price below 16-bar mean by ≥ Nσ)
    - SHORT entry on N-sigma UP (price above 16-bar mean by ≥ Nσ)
    - EXIT on mean re-cross (deviation magnitude has fallen below
      threshold) OR stop-loss
  * `block_window_end - block_window_start ≤ 100`

The strategy never reveals its `n_sigma_x100` threshold or its
`stop_loss_price` — only that some choice exists for which the trade is
consistent. That is the operator's IP.

The 16-bar lookback is a **hard requirement** of the circuit
(`price_observations[16]`) — operators tune `n_sigma_x100`, sizing, and
the stop-loss, never the window length.
"""

from __future__ import annotations

import math

from helios import Direction, MarketSnapshot, StrategyAgent, TradeIntent
from helios.types import Position

LOOKBACK_BARS = 16


class MeanReversionStrategy(StrategyAgent):
    declared_class = "mean_reversion_v1"
    asset_universe = ("USDC", "WKITE", "WETH")
    max_position_size_usd = 10_000
    fee_rate_bps = 2_000  # 20% of realized PnL above HWM

    def __init__(
        self,
        n_sigma_x100: int = 200,
        stop_loss_price_usd: float = 0.0,
        max_slippage_bps: int = 30,
        position_fraction: float = 0.5,
    ) -> None:
        super().__init__()
        # n_sigma_x100 = 200 ⇒ 2.00σ. Stored as int because the circuit's
        # params_hash slot is integer-shaped (see witness.py).
        self._n_sigma_x100 = n_sigma_x100
        self._stop_loss_price = stop_loss_price_usd
        self._max_slippage_bps = max_slippage_bps
        self._position_fraction = position_fraction

    # ── Operator surface ───────────────────────────────────────
    def on_bar(self, asset: str, snapshot: MarketSnapshot) -> TradeIntent | None:
        if asset == "USDC":
            return None  # base asset — never the signal subject
        if len(snapshot.prices) < LOOKBACK_BARS:
            return None  # circuit needs exactly 16 observations
        prices = snapshot.prices[-LOOKBACK_BARS:]
        last_price = prices[-1]
        mean = sum(prices) / LOOKBACK_BARS
        # Population variance across the 16-bar window — matches the circuit's
        # in-circuit `sum_sq_devs` computation (`Σ(16·p_i − Σp)²`).
        variance = sum((p - mean) ** 2 for p in prices) / LOOKBACK_BARS
        stddev = math.sqrt(variance)
        if stddev == 0.0:
            # Degenerate flat history — no z-score; treat as no-signal.
            return None
        z = (last_price - mean) / stddev
        n_sigma = self._n_sigma_x100 / 100.0
        position = self.position_for(asset)

        # ── Stop-loss exit (long-only — Phase 2 reference impl) ─────────
        if position > 0 and self._stop_loss_price > 0 and last_price <= self._stop_loss_price:
            return TradeIntent(
                asset_in=asset,
                asset_out="USDC",
                amount_in_asset=position,
                direction=Direction.EXIT,
                max_slippage_bps=self._max_slippage_bps,
                is_stop_loss=True,
            )

        # ── Long entry: N-sigma DOWN, flat-or-short ─────────────────────
        if z <= -n_sigma and position <= 0:
            return TradeIntent(
                asset_in="USDC",
                asset_out=asset,
                amount_in_usd=self._size(),
                direction=Direction.LONG,
                max_slippage_bps=self._max_slippage_bps,
            )

        # ── Short entry: N-sigma UP, flat-or-long ───────────────────────
        if z >= n_sigma and position >= 0:
            return TradeIntent(
                asset_in=asset,
                asset_out="USDC",
                amount_in_usd=self._size(),
                direction=Direction.SHORT,
                max_slippage_bps=self._max_slippage_bps,
            )

        # ── Mean re-cross exit: deviation magnitude has fallen below ────
        # the entry threshold. Match the circuit's `flip_excess` ≥ 0 gate
        # (lhs ≤ rhs ⇔ |z| ≤ n_sigma).
        if abs(z) < n_sigma and position != 0:
            if position > 0:
                return TradeIntent(
                    asset_in=asset,
                    asset_out="USDC",
                    amount_in_asset=position,
                    direction=Direction.EXIT,
                    max_slippage_bps=self._max_slippage_bps,
                    is_signal_flip=True,
                )
            # short → buy back
            return TradeIntent(
                asset_in="USDC",
                asset_out=asset,
                amount_in_asset=-position,
                direction=Direction.EXIT,
                max_slippage_bps=self._max_slippage_bps,
                is_signal_flip=True,
            )

        return None

    # ── Internal sizing ───────────────────────────────────────
    def _size(self) -> float:
        # PR4: scale entries against NAV (cash + held positions
        # marked-to-market) so a heavily-deployed strategy doesn't
        # collapse new sizes to the leftover cash slice. `size_trade`
        # still clamps to free cash.
        return min(
            float(self.max_position_size_usd),
            self.nav * self._position_fraction,
        )

    # ── Test/runtime helpers ──────────────────────────────────
    def set_capital(self, usd: float) -> None:
        self._available_capital_usd = usd
        # Tests use this helper to simulate a fresh allocation; with no
        # held positions cash == NAV, which keeps `_size()` (now NAV-
        # backed) bit-compatible with the prior cash-backed shape.
        self._nav_usd = usd

    def set_position(self, asset: str, qty: float, avg_price: float, direction: Direction) -> None:
        self._positions[asset] = Position(
            asset=asset, quantity=qty, avg_entry_price=avg_price, direction=direction
        )

    @property
    def n_sigma_x100(self) -> int:
        """Exposed for the witness builder — never log/serialize this."""
        return self._n_sigma_x100

    @property
    def stop_loss_price(self) -> float:
        return self._stop_loss_price

    @property
    def max_slippage_bps(self) -> int:
        return self._max_slippage_bps
