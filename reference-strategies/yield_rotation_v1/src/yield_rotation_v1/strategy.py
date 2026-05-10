"""The reference `YieldRotationStrategy`.

Implements the body of `Helios.md §10.4`'s minimal yield-rotation
example. The runtime layer (oracle polling, witness building, prover
round-trip, on-chain submission) is in `runtime.py` — this module is
just the strategy operator's editable surface: the rotation decision.

Class invariants enforced by `yield_rotation_v1.circom`:
  * Both `m_from` and `m_to` are in the operator-declared allowlist
  * Both APY snapshots are members of the canonical yield-oracle root
  * `apy_to − apy_from ≥ signal_threshold + bridging_cost` (all in bps)
  * `m_from ≠ m_to` and `amount_rotating > 0`
  * `block.number ≤ block_window_end` (on-chain freshness)

The strategy never reveals its `signal_threshold` or `bridging_cost` —
only that *some* threshold and bridging budget exist for which the
rotation is consistent. That's the operator's IP.

The base-class `on_bar` is **not** the right hook for YR (yield ticks
arrive on a different cadence than price bars). The runtime drives
`on_yield_tick` instead, which receives the latest APY snapshot per
market and returns a `RotationIntent | None`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from helios import StrategyAgent
from helios.poseidon import poseidon_hash
from helios.types import MarketSnapshot, TradeIntent

from yield_rotation_v1.types import RotationIntent, YieldTick


class YieldRotationStrategy(StrategyAgent):
    declared_class = "yield_rotation_v1"
    asset_universe: ClassVar[Sequence[str]] = ()  # YR has no asset universe
    max_position_size_usd = 25_000
    fee_rate_bps = 1_500  # 15% performance fee — tighter than directional classes

    def __init__(
        self,
        *,
        allowlisted_markets: Sequence[int],
        signal_threshold_bps: int = 80,
        bridging_cost_bps: int = 30,
        position_fraction: float = 0.5,
    ) -> None:
        super().__init__()
        if not allowlisted_markets:
            raise ValueError("allowlisted_markets must be non-empty")
        if signal_threshold_bps < 0 or bridging_cost_bps < 0:
            raise ValueError("threshold + bridging cost must be non-negative")
        self._allowlist = tuple(allowlisted_markets)
        self._signal_threshold_bps = signal_threshold_bps
        self._bridging_cost_bps = bridging_cost_bps
        self._position_fraction = position_fraction
        # YR doesn't track per-asset positions the way directional
        # strategies do; we track the active market id (or None) here.
        self._active_market: int | None = None

    # Bound exposure used by both the witness builder and
    # `ensure_params_committed` on container start. YR's hash is
    # narrower than the directional classes (only two operator
    # bounds — threshold + bridging cost) to match
    # `circuits/yield_rotation_v1.circom`'s param vector.
    def params_hash(self) -> bytes:
        return poseidon_hash([self._signal_threshold_bps, self._bridging_cost_bps]).to_bytes(
            32, "big"
        )

    # ── Operator surface ───────────────────────────────────────
    def on_bar(self, asset: str, snapshot: MarketSnapshot) -> TradeIntent | None:
        """Yield-rotation strategies do not respond to price bars. The
        SDK base hook is overridden to a no-op so the runtime never
        accidentally drives `on_bar` against this class."""
        del asset, snapshot
        return None

    def on_yield_tick(self, ticks: dict[int, YieldTick]) -> RotationIntent | None:
        """Called once per yield-cadence tick by the runtime.

        `ticks` is a snapshot of the latest APY (in bps × 1e6) for every
        allowlisted market the operator subscribes to. The reference
        impl rotates the entire active-market position into the
        highest-APY allowlisted market when the differential beats
        `signal_threshold + bridging_cost` net of fees.
        """
        if not ticks:
            return None
        # Limit to allowlisted markets the operator has subscribed to.
        candidates = {m: t for m, t in ticks.items() if m in self._allowlist}
        if len(candidates) < 2:
            return None

        # Pick best (highest APY) destination.
        best_market = max(candidates, key=lambda m: candidates[m].apy_bps_e6)
        # Operator-side APY is bps × 1e6; convert to plain bps for the circuit.
        best_apy_bps = _e6_to_bps(candidates[best_market].apy_bps_e6)

        # If we're already in the best market, hold.
        if self._active_market == best_market:
            return None

        # Choose source: current position (if any) else worst available.
        # Phase-3 review MEDIUM (deferred): when `_active_market is None`
        # the strategy synthesizes `from_market = min(candidates)` so the
        # first tick produces a "rotation" that is really the initial
        # deployment. The driver in `helios.backtest.run_yield_backtest`
        # tolerates this (line ~624 comment) and the test suite asserts
        # the count includes it. A clean fix is structural — either an
        # explicit `InitialDeploymentIntent` type or a `first_tick` flag
        # on `Rotation` so reporting can distinguish — and is bigger than
        # this MEDIUM batch warrants. Tracking via the followup queue.
        if self._active_market is not None and self._active_market in candidates:
            from_market = self._active_market
        else:
            from_market = min(candidates, key=lambda m: candidates[m].apy_bps_e6)

        if from_market == best_market:
            return None

        from_apy_bps = _e6_to_bps(candidates[from_market].apy_bps_e6)
        differential = best_apy_bps - from_apy_bps
        required = self._signal_threshold_bps + self._bridging_cost_bps
        if differential < required:
            return None

        return RotationIntent(
            m_from=from_market,
            m_to=best_market,
            amount_in_usd=self._size(),
            apy_from_bps=from_apy_bps,
            apy_to_bps=best_apy_bps,
        )

    # ── Internal sizing ───────────────────────────────────────
    def _size(self) -> float:
        return min(
            float(self.max_position_size_usd),
            self.available_capital * self._position_fraction,
        )

    # ── Test/runtime helpers ──────────────────────────────────
    def set_capital(self, usd: float) -> None:
        self._available_capital_usd = usd

    def set_active_market(self, market_id: int | None) -> None:
        self._active_market = market_id

    @property
    def active_market(self) -> int | None:
        return self._active_market

    @property
    def allowlisted_markets(self) -> tuple[int, ...]:
        return self._allowlist

    @property
    def signal_threshold_bps(self) -> int:
        """Exposed for the witness builder — never log/serialize this."""
        return self._signal_threshold_bps

    @property
    def bridging_cost_bps(self) -> int:
        return self._bridging_cost_bps


def _e6_to_bps(apy_bps_e6: int) -> int:
    """Convert YieldStore's `apy_bps_e6` to plain bps (rounding down).

    The circuit's `signal_threshold` and `bridging_cost` are bps; the
    oracle stores `bps × 1e6`. The conversion is lossy by design — the
    circuit's 16-bit range checks (`apyFromBits.in <== apy_from`) bound
    APYs at 65_535 bps (~655%), so we compress at the boundary.
    """
    return apy_bps_e6 // 1_000_000
