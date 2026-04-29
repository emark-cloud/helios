"""Aave-v3 stub yield source for Phase 2 scenario mode.

Returns scripted APY ticks that ramp gently then dip — the goal is to
give `yield_rotation_v1` strategies a real signal to chase in CI. Real
Aave reserve reads land in Phase 5 (`oracle.sources.yield_aave`).

Two markets are pre-seeded: `aave-v3:USDC` (the "from" market in the
canonical scenario) and `aave-v3:USDT` (the "to" market). Operators
can wire additional markets via `markets=` at construction.
"""

from __future__ import annotations

from threading import Lock
from time import time

from oracle.sources.yield_base import YieldQuote, YieldSource, YieldSourceError

# (apy_bps_e6,) ticks. 5.25% APY → 525 bps → 525_000_000 in this scale.
_DEFAULT_TICKS: dict[str, list[int]] = {
    # USDC drifts down 5.25% → 4.10% over 6 ticks.
    "aave-v3:USDC": [525_000_000, 510_000_000, 480_000_000, 450_000_000, 425_000_000, 410_000_000],
    # USDT holds steady around 5.0% — the rotation target if differential exceeds threshold.
    "aave-v3:USDT": [500_000_000, 502_000_000, 498_000_000, 501_000_000, 499_000_000, 500_000_000],
}


class AaveStubSource(YieldSource):
    name = "aave-v3-stub"

    def __init__(self, markets: dict[str, list[int]] | None = None) -> None:
        self._series: dict[str, list[int]] = dict(markets or _DEFAULT_TICKS)
        self._cursors: dict[str, int] = dict.fromkeys(self._series.keys(), 0)
        self._lock = Lock()

    async def fetch(self, market_id: str) -> YieldQuote:
        ticks = self._series.get(market_id)
        if not ticks:
            raise YieldSourceError(f"aave-v3-stub: no series for {market_id!r}")
        with self._lock:
            idx = self._cursors[market_id]
            apy = ticks[idx]
            self._cursors[market_id] = min(idx + 1, len(ticks) - 1)
        # Walltime is supplied by the caller (the yield poller) — stub
        # series is ordinal, not time-based.
        return YieldQuote(
            market_id=market_id,
            apy_bps_e6=apy,
            timestamp_ms=int(time() * 1000),
            source=self.name,
        )

    def reset(self) -> None:
        with self._lock:
            for k in self._cursors:
                self._cursors[k] = 0
