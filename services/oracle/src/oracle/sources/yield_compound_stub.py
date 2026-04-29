"""Compound-v3 stub yield source for Phase 2 scenario mode.

Companion to `yield_aave_stub`. The two stubs together let the WS1.C
yield-rotation circuit see a divergent APY across Aave and Compound
markets and rotate accordingly. Real Compound reads land in Phase 5.
"""

from __future__ import annotations

from threading import Lock
from time import time

from oracle.sources.yield_base import YieldQuote, YieldSource, YieldSourceError

# Compound USDC trades at a slight discount to Aave's USDC for most
# scenario ticks, then crosses over — gives the rotation strategy a
# moment to switch sides on a real APY differential rather than noise.
_DEFAULT_TICKS: dict[str, list[int]] = {
    "compound-v3:USDC": [
        510_000_000,
        515_000_000,
        520_000_000,
        525_000_000,
        530_000_000,
        535_000_000,
    ],
    "compound-v3:USDT": [
        495_000_000,
        497_000_000,
        499_000_000,
        500_000_000,
        501_000_000,
        503_000_000,
    ],
}


class CompoundStubSource(YieldSource):
    name = "compound-v3-stub"

    def __init__(self, markets: dict[str, list[int]] | None = None) -> None:
        self._series: dict[str, list[int]] = dict(markets or _DEFAULT_TICKS)
        self._cursors: dict[str, int] = dict.fromkeys(self._series.keys(), 0)
        self._lock = Lock()

    async def fetch(self, market_id: str) -> YieldQuote:
        ticks = self._series.get(market_id)
        if not ticks:
            raise YieldSourceError(f"compound-v3-stub: no series for {market_id!r}")
        with self._lock:
            idx = self._cursors[market_id]
            apy = ticks[idx]
            self._cursors[market_id] = min(idx + 1, len(ticks) - 1)
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
