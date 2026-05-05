"""BTC realized-vol + 1-year vol-percentile reads for regime detection.

Helix-lite v1 pins `regime=NORMAL`, so these helpers are not on the v1
critical path. They ship in v1 so any third-party allocator can adopt
regime adaptivity earlier than Helix does, and so Helix-v2 has the
data plumbing ready to go.

Why an HTTP-reader instead of a Web3 read of `OraclePriceAnchor`:
the on-chain anchor stores only a Poseidon-rolled fingerprint per
window — you can't reconstruct the per-snapshot price series from it.
The Helios oracle service exposes `GET /v1/snapshots/recent` for that
(`services/oracle/src/oracle/service.py:180`). Tests inject a
`StaticMarketData` fake so the calculation is exercised without
touching either the oracle service or HTTP.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from typing import Protocol

import httpx

from helios_allocator.helpers._math import (
    log_returns,
    percentiles,
    realized_volatility,
)


class MarketDataReader(Protocol):
    """Minimal contract a market-data source must satisfy. Returns
    chronological daily close prices, oldest → newest, capped at
    `days` observations."""

    async def daily_close_prices(self, asset: str, *, days: int) -> list[float]: ...


class StaticMarketData:
    """In-memory reader for tests, backtests, and bootstrapping
    allocators before the on-chain anchor data path is wired up.
    Stores chronological daily closes per asset, oldest → newest."""

    def __init__(self, daily_closes: Mapping[str, Sequence[float]]) -> None:
        self._closes: dict[str, list[float]] = {k: list(v) for k, v in daily_closes.items()}

    async def daily_close_prices(self, asset: str, *, days: int) -> list[float]:
        if days <= 0:
            return []
        series = self._closes.get(asset, [])
        return list(series[-days:])


class OracleHTTPReader:
    """Reads recent snapshots from a running Helios oracle service and
    downsamples them to one close per UTC day.

    Caveat: `services/oracle` caps `n` at 512 per request. For asset
    feeds at 1-minute cadence that's roughly 8 hours of history, far
    short of the year-long window `btc_vol_percentiles_1y` wants. The
    oracle either needs a paginated history endpoint or this reader
    needs to maintain its own rolling tape. Tracked for Helix-v2.
    """

    _MAX_PER_REQUEST = 512  # matches `services/oracle/src/oracle/service.py:183`.

    def __init__(
        self,
        endpoint: str,
        client: httpx.AsyncClient | None = None,
        *,
        cache_ttl_sec: float = 3600.0,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None
        self._cache: dict[str, tuple[float, list[float]]] = {}
        self._cache_ttl = cache_ttl_sec

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def daily_close_prices(self, asset: str, *, days: int) -> list[float]:
        if days <= 0:
            return []
        key = f"{asset}:{days}"
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached is not None and (now - cached[0]) < self._cache_ttl:
            return list(cached[1])
        n = min(days * 1440, self._MAX_PER_REQUEST)
        resp = await self._client.get(
            f"{self._endpoint}/v1/snapshots/recent",
            params={"asset": asset, "n": n},
        )
        resp.raise_for_status()
        body = resp.json()
        prices = self._downsample_daily(list(body.get("snapshots") or []))
        self._cache[key] = (now, list(prices))
        return prices

    @staticmethod
    def _downsample_daily(snaps: list[dict]) -> list[float]:
        """One close price per UTC day, oldest → newest."""
        if not snaps:
            return []
        # Oracle returns newest first; reverse so the per-day
        # last-write-wins rule yields the day's closing print.
        ordered = list(reversed(snaps))
        by_day: dict[int, float] = {}
        for s in ordered:
            ts_ms = int(s["timestamp_ms"])
            day = ts_ms // 86_400_000
            by_day[day] = float(s["price_e18"]) / 1e18
        return [by_day[d] for d in sorted(by_day.keys())]


async def btc_realized_vol_30d(reader: MarketDataReader) -> float:
    """Annualized 30-day realized volatility of BTC log-returns."""
    prices = await reader.daily_close_prices("BTC", days=30)
    return realized_volatility(log_returns(prices))


async def btc_vol_percentiles_1y(reader: MarketDataReader) -> dict[str, float]:
    """30-day rolling realized-vol percentiles over the last ~1 year.

    Pulls 365 daily closes, computes a rolling 30-day vol series from
    the resulting log-returns, returns the `(p20, p80)` band consumed
    by `detect_regime`. Falls back to `{p20: 0, p80: inf}` when the
    history is too short — this leaves `detect_regime` permanently in
    NORMAL rather than mis-classifying on thin data.
    """
    prices = await reader.daily_close_prices("BTC", days=365)
    returns = log_returns(prices)
    if len(returns) < 30:
        return {"p20": 0.0, "p80": float("inf")}
    rolling: list[float] = []
    for i in range(30, len(returns) + 1):
        rolling.append(realized_volatility(returns[i - 30 : i]))
    return percentiles(rolling, [0.20, 0.80])
