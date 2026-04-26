"""Scenario replay — deterministic price series for the demo.

When `SCENARIO_MODE=1`, the oracle reads a JSON file (default
`scenarios/phase1-drawdown.json`) and replays one tick per call.

JSON shape:

    {
      "assets": {
        "KITE/USDT": [
          { "ts_ms": 0,    "price_e18": "1500000000000000000" },
          { "ts_ms": 60000, "price_e18": "1485000000000000000" },
          ...
        ],
        "ETH/USDT": [...]
      }
    }

Time is replayed in walltime: the first tick is returned at scenario
start, then ticks are paced by the gap between `ts_ms` values.
For Phase 1's deterministic demo we instead fetch the next tick on each
`fetch()` call (the poller's cadence handles pacing).
"""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from oracle.sources.base import PriceQuote, SourceError


class ScenarioSource:
    name = "scenario"

    def __init__(self, scenario_path: str | Path) -> None:
        path = Path(scenario_path)
        if not path.exists():
            raise FileNotFoundError(f"scenario file not found: {path}")
        data = json.loads(path.read_text())
        assets = data.get("assets") or {}
        if not assets:
            raise ValueError(f"scenario file has no assets: {path}")
        self._series: dict[str, list[dict[str, int | str]]] = assets
        self._cursors: dict[str, int] = dict.fromkeys(assets.keys(), 0)
        self._lock = Lock()  # poller is single-task per asset, but keep us honest

    async def fetch(self, asset: str) -> PriceQuote:
        ticks = self._series.get(asset)
        if not ticks:
            raise SourceError(f"scenario: no series for {asset!r}")
        with self._lock:
            idx = self._cursors[asset]
            tick = ticks[idx]
            # Hold the last tick once the series is exhausted (steady state for the
            # rest of the demo) rather than wrapping — wrapping would re-trigger
            # whatever drawdown the scenario embeds.
            self._cursors[asset] = min(idx + 1, len(ticks) - 1)
        return PriceQuote(
            asset=asset,
            price_e18=int(tick["price_e18"]),
            timestamp_ms=int(tick["ts_ms"]),
            source=self.name,
        )

    def reset(self) -> None:
        with self._lock:
            for k in self._cursors:
                self._cursors[k] = 0
