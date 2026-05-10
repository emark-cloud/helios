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
from oracle.service import _ALIASES, Settings, _resolve_asset, build_app

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
        # Poseidon root over BN254: decimal field-element string + 32-byte hex.
        assert rbody["root"].isdigit() and 0 < int(rbody["root"]) < (1 << 254)
        assert rbody["root_bytes32"].startswith("0x") and len(rbody["root_bytes32"]) == 66
        assert int(rbody["root_bytes32"], 16) == int(rbody["root"])
        assert rbody["hash"] == "poseidon"
        assert rbody["head_timestamp_ms"] == 120000

        missing = await client.get("/v1/snapshots/recent", params={"asset": "BTC/USDT", "n": 5})
        assert missing.status_code == 404


def test_alias_table_covers_phase6_universe() -> None:
    """The reference strategies declare their `asset_universe` in token-symbol
    form (`WBTC`, `WETH`, `WSOL`) so the operator-facing API stays in vault
    token names. The oracle keys its rings by exchange-pair names. Lock the
    alias table so a future rename here is caught by CI before strategies
    start 404'ing on the live oracle."""
    assert _ALIASES == {
        "WBTC": "BTC/USDT",
        "WETH": "ETH/USDT",
        "WSOL": "SOL/USDT",
    }
    # Unknown / canonical names round-trip unchanged.
    assert _resolve_asset("BTC/USDT") == "BTC/USDT"
    assert _resolve_asset("KITE/USDT") == "KITE/USDT"
    assert _resolve_asset("WBTC") == "BTC/USDT"


@pytest.mark.asyncio
async def test_alias_resolves_to_canonical_snapshots() -> None:
    """A `WETH` request must return the same snapshots as `ETH/USDT` —
    snapshot store is keyed by canonical name; aliases never bifurcate
    state. Regression on the WS9 fix that unblocked the strategy runtime
    from a 404 cascade against the live oracle."""
    settings = Settings()  # type: ignore[call-arg]
    app = build_app(settings)
    poller = app.state.poller
    for _ in range(3):
        await poller.tick_once()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        canonical = await client.get("/v1/snapshots/recent", params={"asset": "ETH/USDT", "n": 3})
        assert canonical.status_code == 200, canonical.text
        aliased = await client.get("/v1/snapshots/recent", params={"asset": "WETH", "n": 3})
        assert aliased.status_code == 200, aliased.text
        # The route preserves the canonical asset name in the response
        # (snapshot store is keyed by canonical), but the timestamps,
        # prices, and signatures are identical to the canonical fetch.
        c, a = canonical.json(), aliased.json()
        assert c["n"] == a["n"]
        assert [s["timestamp_ms"] for s in c["snapshots"]] == [
            s["timestamp_ms"] for s in a["snapshots"]
        ]
        assert [s["digest"] for s in c["snapshots"]] == [s["digest"] for s in a["snapshots"]]

        # `/snapshots/root` honors the alias too.
        root_c = await client.get("/v1/snapshots/root", params={"asset": "ETH/USDT", "n": 3})
        root_a = await client.get("/v1/snapshots/root", params={"asset": "WETH", "n": 3})
        assert root_c.status_code == 200 and root_a.status_code == 200
        assert root_c.json()["root_bytes32"] == root_a.json()["root_bytes32"]
