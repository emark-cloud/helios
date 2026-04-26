"""End-to-end service test in scenario mode.

Brings up the FastAPI app pointed at the committed phase-1 scenario file,
ticks the poller deterministically, and asserts the snapshot endpoints
return well-formed signed data.
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
    # Wipe ORACLE_*/SCENARIO_* envs so Settings() picks up our overrides cleanly,
    # then drive overrides via env vars (pydantic-settings honors validation_alias
    # for env lookup but not for direct kwargs).
    for k in list(os.environ):
        if k.startswith("ORACLE_") or k in {"SCENARIO_MODE", "SCENARIO_FILE"}:
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SCENARIO_MODE", "1")
    monkeypatch.setenv("SCENARIO_FILE", str(SCENARIO_PATH))
    monkeypatch.setenv("ORACLE_ASSETS", "KITE/USDT,ETH/USDT")
    monkeypatch.setenv("ORACLE_BAR_INTERVAL_SEC", "1")


@pytest.mark.asyncio
async def test_scenario_mode_serves_signed_snapshots() -> None:
    settings = Settings()  # type: ignore[call-arg]
    app = build_app(settings)
    poller = app.state.poller

    # Advance the poller deterministically without sleeping.
    for _ in range(3):
        await poller.tick_once()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        info = await client.get("/v1/")
        assert info.status_code == 200
        info_json = info.json()
        assert info_json["scenario_mode"] == 1
        assert "KITE/USDT" in info_json["assets"]

        recent = await client.get("/v1/snapshots/recent", params={"asset": "KITE/USDT", "n": 5})
        assert recent.status_code == 200
        body = recent.json()
        assert body["n"] == 3, body
        # Newest first: ts_ms = 120000, 60000, 0.
        assert [s["timestamp_ms"] for s in body["snapshots"]] == [120000, 60000, 0]
        for snap in body["snapshots"]:
            assert snap["digest"].startswith("0x") and len(snap["digest"]) == 66
            assert snap["signature"].startswith("0x") and len(snap["signature"]) == 132
            assert snap["source"] == "scenario"

        root = await client.get("/v1/snapshots/root", params={"asset": "KITE/USDT", "n": 3})
        assert root.status_code == 200
        rbody = root.json()
        assert rbody["root"].startswith("0x") and len(rbody["root"]) == 66
        assert rbody["hash"] == "keccak256"
        assert rbody["head_timestamp_ms"] == 120000

        missing = await client.get("/v1/snapshots/recent", params={"asset": "BTC/USDT", "n": 5})
        assert missing.status_code == 404
