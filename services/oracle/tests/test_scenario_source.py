"""Scenario replay source — deterministic ticks from a JSON file."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from oracle.sources.base import SourceError
from oracle.sources.scenario import ScenarioSource


@pytest.fixture()
def scenario_path(tmp_path: Path) -> Path:
    p = tmp_path / "tiny.json"
    p.write_text(
        json.dumps(
            {
                "assets": {
                    "KITE/USDT": [
                        {"ts_ms": 0, "price_e18": "1500000000000000000"},
                        {"ts_ms": 60000, "price_e18": "1490000000000000000"},
                    ]
                }
            }
        )
    )
    return p


@pytest.mark.asyncio
async def test_scenario_advances_each_call(scenario_path: Path) -> None:
    s = ScenarioSource(scenario_path)
    q1 = await s.fetch("KITE/USDT")
    q2 = await s.fetch("KITE/USDT")
    assert q1.timestamp_ms == 0
    assert q2.timestamp_ms == 60000
    # After the series exhausts, hold the last tick.
    q3 = await s.fetch("KITE/USDT")
    assert q3.timestamp_ms == 60000
    assert q3.price_e18 == 1_490_000_000_000_000_000


@pytest.mark.asyncio
async def test_scenario_unknown_asset_raises(scenario_path: Path) -> None:
    s = ScenarioSource(scenario_path)
    with pytest.raises(SourceError):
        await s.fetch("ETH/USDT")


@pytest.mark.asyncio
async def test_scenario_reset_returns_to_start(scenario_path: Path) -> None:
    s = ScenarioSource(scenario_path)
    await s.fetch("KITE/USDT")
    await s.fetch("KITE/USDT")
    s.reset()
    q = await s.fetch("KITE/USDT")
    assert q.timestamp_ms == 0
