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
from helios.poseidon import poseidon_hash
from helios.sizing import nav_target_notional


class MomentumStrategy(StrategyAgent):
    declared_class = "momentum_v1"
    # Phase-6 multi-asset default universe (Kite testnet real-P&L). USDC
    # remains the base asset (the `if asset == "USDC"` guard in `on_bar`
    # keeps it out of the signal subjects). WBTC/WETH/SOL gain real
    # oracle prices via the BTC/ETH/SOL Binance/Coingecko sources, so
    # the strategy actually moves NAV when those markets move.
    # Per-deploy chains override via the `asset_universe` __init__ arg
    # — symbolic order MUST match `MOMENTUM_ASSET_UNIVERSE_ADDRESSES_JSON`
    # slot order; the runtime asserts lockstep at startup.
    asset_universe: tuple[str, ...] = ("USDC", "WBTC", "WETH", "WSOL")
    max_position_size_usd = 10_000
    fee_rate_bps = 2_000  # 20% of realized PnL above HWM

    def __init__(
        self,
        signal_threshold: float = 0.015,
        lookback_bars: int = 10,
        max_slippage_bps: int = 30,
        position_fraction: float = 0.5,
        stop_loss_price: float = 0.0,
        asset_universe: tuple[str, ...] | None = None,
    ) -> None:
        super().__init__()
        # `signal_threshold` is private witness data — not serialized
        # alongside trades; only its existence is proven.
        self._signal_threshold = signal_threshold
        self._lookback = lookback_bars
        self._max_slippage_bps = max_slippage_bps
        self._position_fraction = position_fraction
        self._stop_loss_price = stop_loss_price
        if asset_universe is not None:
            if not asset_universe or asset_universe[0] != "USDC":
                raise ValueError(
                    "asset_universe must be a non-empty tuple beginning with 'USDC' "
                    f"(got {asset_universe!r})"
                )
            self.asset_universe = tuple(asset_universe)

    # ── Bound exposure (used both by the witness builder + by
    # `ensure_params_committed` on container start). The on-chain
    # registry stores the bytes32 returned here; every Groth16
    # `executeWithProof` is checked against it (`StrategyVault.sol:470`).
    def params_hash(self) -> bytes:
        max_position_size_e18 = self.max_position_size_usd * 10**18
        signal_threshold_bps = round(self._signal_threshold * 10_000)
        stop_loss_price_e18 = int(self._stop_loss_price * 10**18)
        return poseidon_hash(
            [
                max_position_size_e18,
                self._max_slippage_bps,
                signal_threshold_bps,
                stop_loss_price_e18,
            ]
        ).to_bytes(32, "big")

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
                is_nav_targeted=True,
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
        # WS4 PR 3/3: delegate to the SDK's `nav_target_notional` helper.
        # Returns `min(self.nav * fraction, max_position_size_usd)`. The
        # accompanying `is_nav_targeted=True` on the emitted TradeIntent
        # tells the engine's `size_trade` to clamp against NAV rather
        # than `available_capital` — the right rule for "target X% of
        # NAV per trade" sizing on a half-deployed strategy.
        return nav_target_notional(self, self._position_fraction)

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
