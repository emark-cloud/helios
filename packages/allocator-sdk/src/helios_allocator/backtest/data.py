"""Goldsky-backed historical NAV fetcher with on-disk cache.

CLI users run `helios-allocator backtest --period 90d --strategies …`;
that command resolves to `fetch_nav_series` here, which pulls
`NAVSnapshot` rows from the subgraph for each strategy and converts
them into the daily series the runner consumes.

A rerun against the same period + strategy set hits the local cache
under `~/.cache/helios/backtest/<endpoint-hash>/<strategy>.json` rather
than re-querying. The cache is content-addressed by `(endpoint,
strategy_id, start, end)` so endpoint changes invalidate cleanly.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from helios_allocator.backtest.runner import StrategyNavSeries

_DEFAULT_CACHE_DIR = Path(
    os.environ.get(
        "HELIOS_BACKTEST_CACHE_DIR",
        str(Path.home() / ".cache" / "helios" / "backtest"),
    )
)


_QUERY_NAV_RANGE = """
query NavRange($strategy: Bytes!, $start: BigInt!, $end: BigInt!) {
  navSnapshots(
    where: { strategy: $strategy, timestamp_gte: $start, timestamp_lte: $end }
    orderBy: timestamp
    orderDirection: asc
    first: 1000
  ) {
    timestamp
    totalNAV
  }
}
"""


@dataclass(frozen=True, slots=True)
class _Snapshot:
    timestamp: int
    nav_usd: float


class GoldskyHistoricalClient:
    """Pulls NAVSnapshot ranges per strategy.

    Mirrors `runtime.goldsky.AllocatorGoldsky`'s offline-tolerant
    posture: an unset endpoint returns empty series rather than
    raising, so smoke tests can exercise the cache layer without a
    network.
    """

    def __init__(
        self,
        endpoint: str,
        client: httpx.AsyncClient | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._owns_client = client is None
        self._cache_dir = cache_dir or _DEFAULT_CACHE_DIR

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def fetch_nav(
        self,
        strategy_id: str,
        start: int,
        end: int,
    ) -> list[_Snapshot]:
        cached = self._cache_read(strategy_id, start, end)
        if cached is not None:
            return cached
        if not self._endpoint:
            return []
        resp = await self._client.post(
            self._endpoint,
            json={
                "query": _QUERY_NAV_RANGE,
                "variables": {
                    "strategy": strategy_id,
                    "start": str(start),
                    "end": str(end),
                },
            },
        )
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        if "errors" in body:
            raise RuntimeError(f"goldsky errors: {body['errors']}")
        rows = list((body.get("data") or {}).get("navSnapshots") or [])
        snaps = [
            _Snapshot(timestamp=int(r["timestamp"]), nav_usd=float(int(r["totalNAV"]) / 1e6))
            for r in rows
        ]
        self._cache_write(strategy_id, start, end, snaps)
        return snaps

    def _cache_path(self, strategy_id: str, start: int, end: int) -> Path:
        h = hashlib.sha256(self._endpoint.encode()).hexdigest()[:12]
        return self._cache_dir / h / f"{strategy_id.lower()}_{start}_{end}.json"

    def _cache_read(self, strategy_id: str, start: int, end: int) -> list[_Snapshot] | None:
        p = self._cache_path(strategy_id, start, end)
        if not p.is_file():
            return None
        raw = json.loads(p.read_text(encoding="utf-8"))
        return [_Snapshot(timestamp=int(r["timestamp"]), nav_usd=float(r["nav_usd"])) for r in raw]

    def _cache_write(self, strategy_id: str, start: int, end: int, snaps: list[_Snapshot]) -> None:
        p = self._cache_path(strategy_id, start, end)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = [{"timestamp": s.timestamp, "nav_usd": s.nav_usd} for s in snaps]
        p.write_text(json.dumps(payload), encoding="utf-8")


def _resample_daily(snaps: list[_Snapshot], start: int, days: int) -> list[float]:
    """Forward-fill snapshots into a `days+1`-long daily NAV grid."""
    if not snaps:
        return [0.0] * (days + 1)
    grid: list[float] = []
    cursor = 0
    last = snaps[0].nav_usd
    for d in range(days + 1):
        boundary = start + d * 86_400
        while cursor < len(snaps) and snaps[cursor].timestamp <= boundary:
            last = snaps[cursor].nav_usd
            cursor += 1
        grid.append(last)
    return grid


async def fetch_nav_series(
    client: GoldskyHistoricalClient,
    *,
    strategies: list[StrategyNavSeries],
    period_days: int,
    end_ts: int | None = None,
) -> list[StrategyNavSeries]:
    """Hydrate `StrategyNavSeries.daily_navs` from Goldsky.

    Each input carries the static metadata (id, class, fee, capacity);
    this function fills in the `daily_navs` field. Returns a fresh list
    of frozen instances — the input objects are not mutated.
    """
    end = end_ts if end_ts is not None else int(time.time())
    start = end - period_days * 86_400
    out: list[StrategyNavSeries] = []
    for s in strategies:
        snaps = await client.fetch_nav(s.strategy_id, start, end)
        navs = _resample_daily(snaps, start, period_days)
        out.append(
            StrategyNavSeries(
                strategy_id=s.strategy_id,
                declared_class=s.declared_class,
                fee_rate_bps=s.fee_rate_bps,
                stake_amount_usd=s.stake_amount_usd,
                max_capacity_usd=s.max_capacity_usd,
                reputation_score=s.reputation_score,
                chain_id=s.chain_id,
                operator=s.operator,
                trades_attested=s.trades_attested,
                daily_navs=tuple(navs),
            )
        )
    return out


__all__ = [
    "GoldskyHistoricalClient",
    "fetch_nav_series",
]
