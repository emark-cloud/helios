"""Yield-snapshot endpoints — recent + root + markets in scenario mode.

The yield poller polls the AaveStub + CompoundStub feeders deterministically;
this asserts the FastAPI surface returns well-formed signed snapshots and a
Poseidon-chained root that matches what `yield_rotation_v1` strategies will
hash against.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest
from oracle.service import Settings, build_app

REPO_ROOT = Path(__file__).resolve().parents[3]
SCENARIO_PATH = REPO_ROOT / "scenarios" / "phase1-drawdown.json"


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in list(os.environ):
        if k.startswith("ORACLE_") or k in {"SCENARIO_MODE", "SCENARIO_FILE"}:
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SCENARIO_MODE", "1")
    monkeypatch.setenv("SCENARIO_FILE", str(SCENARIO_PATH))
    monkeypatch.setenv("ORACLE_ASSETS", "KITE/USDT,ETH/USDT")
    monkeypatch.setenv("ORACLE_BAR_INTERVAL_SEC", "1")
    monkeypatch.setenv(
        "ORACLE_YIELD_MARKETS",
        "aave-v3:USDC,aave-v3:USDT,compound-v3:USDC,compound-v3:USDT",
    )
    monkeypatch.setenv("ORACLE_YIELD_INTERVAL_SEC", "1")


@pytest.mark.asyncio
async def test_yield_endpoint_returns_signed_snapshots() -> None:
    settings = Settings()  # type: ignore[call-arg]
    app = build_app(settings)
    yield_poller = app.state.yield_poller

    # Drive the yield poller deterministically — three ticks → three
    # snapshots per market in the AAVE/Compound stub series.
    for _ in range(3):
        await yield_poller.tick_once()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        markets = await client.get("/v1/yield/markets")
        assert markets.status_code == 200
        mbody = markets.json()
        assert "aave-v3:USDC" in mbody["configured"]
        assert "aave-v3:USDC" in mbody["active"]

        recent = await client.get(
            "/v1/yield/recent", params={"market_id": "aave-v3:USDC", "n": 3}
        )
        assert recent.status_code == 200
        body = recent.json()
        assert body["n"] == 3
        for snap in body["snapshots"]:
            assert snap["market_id"] == "aave-v3:USDC"
            assert int(snap["apy_bps_e6"]) > 0
            assert snap["digest"].startswith("0x") and len(snap["digest"]) == 66
            assert snap["signature"].startswith("0x") and len(snap["signature"]) == 132
            assert snap["source"].startswith("aave")

        root = await client.get(
            "/v1/yield/root", params={"market_id": "aave-v3:USDC", "n": 3}
        )
        assert root.status_code == 200
        rbody = root.json()
        assert rbody["root"].isdigit() and 0 < int(rbody["root"]) < (1 << 254)
        assert rbody["root_bytes32"].startswith("0x") and len(rbody["root_bytes32"]) == 66
        assert int(rbody["root_bytes32"], 16) == int(rbody["root"])
        assert rbody["hash"] == "poseidon"

        missing = await client.get(
            "/v1/yield/recent", params={"market_id": "venus:USDC", "n": 3}
        )
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_yield_recent_empty_before_polling() -> None:
    """Before the yield poller runs, the store has no snapshots — endpoint
    returns an empty list rather than 404."""
    settings = Settings()  # type: ignore[call-arg]
    app = build_app(settings)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        recent = await client.get(
            "/v1/yield/recent", params={"market_id": "aave-v3:USDC", "n": 3}
        )
        assert recent.status_code == 200
        body = recent.json()
        assert body["n"] == 0
        assert body["snapshots"] == []
