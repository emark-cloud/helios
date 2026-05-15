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
from pydantic import ValidationError

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


@pytest.mark.asyncio
async def test_endpoints_serve_committed_view_when_mirror_populated() -> None:
    """When `CommitMirror` has a window for the asset and it covers the
    requested `n`, both `/snapshots/recent` and `/snapshots/root` must
    return that window verbatim (`view=committed`). This guarantees
    strategy + on-chain anchor see the same Poseidon root, which is what
    the mirror was introduced to fix (`UnknownOracleRoot()` reverts on
    every trade when the live ring advanced between fetch and submit)."""
    settings = Settings()  # type: ignore[call-arg]
    app = build_app(settings)
    poller = app.state.poller
    commit_mirror = app.state.commit_mirror
    store = app.state.store

    # Tick the poller so the live ring has a few snapshots, then pin a
    # deliberately-different window into the mirror so we can tell which
    # source the handler chose.
    for _ in range(3):
        await poller.tick_once()

    live = store.recent("ETH/USDT", 3)
    assert len(live) == 3, "preconditions: poller must have filled the live ring"

    # Build the committed window by reversing the live one — both timestamps
    # and price ordering differ, so a `view=committed` response will be
    # visibly different from `view=live`. (Mirror stores newest-first like
    # the live ring; we reverse to fabricate a distinct window.)
    committed_snaps = list(reversed(live))
    fake_root = 0xFEEDFACE_DEAD_BEEF
    commit_mirror.record(
        "ETH/USDT",
        committed_snaps,
        fake_root,
        window_end_ms=committed_snaps[0].timestamp_ms,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        recent = await client.get("/v1/snapshots/recent", params={"asset": "ETH/USDT", "n": 3})
        assert recent.status_code == 200
        body = recent.json()
        assert body["view"] == "committed"
        assert [s["timestamp_ms"] for s in body["snapshots"]] == [
            s.timestamp_ms for s in committed_snaps
        ]

        root = await client.get("/v1/snapshots/root", params={"asset": "ETH/USDT", "n": 3})
        rbody = root.json()
        assert rbody["view"] == "committed"
        assert int(rbody["root"]) == fake_root
        assert int(rbody["root_bytes32"], 16) == fake_root


@pytest.mark.asyncio
async def test_endpoints_fall_back_to_live_when_mirror_too_shallow() -> None:
    """If the committed window covers fewer snapshots than the caller
    requested, the handler must fall through to the live ring rather
    than silently serve a short window. Otherwise a strategy with
    `LOOKBACK_BARS=16` could be fed a 3-snapshot committed slice and
    compute a root over the wrong window."""
    settings = Settings()  # type: ignore[call-arg]
    app = build_app(settings)
    poller = app.state.poller
    commit_mirror = app.state.commit_mirror
    store = app.state.store

    for _ in range(3):
        await poller.tick_once()

    # Record a committed window with only 1 snapshot; live ring has 3.
    one = store.recent("KITE/USDT", 1)
    assert len(one) == 1
    commit_mirror.record("KITE/USDT", one, root=0xDEAD, window_end_ms=one[0].timestamp_ms)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # n=3 > committed depth 1 → fall back to live.
        recent = await client.get("/v1/snapshots/recent", params={"asset": "KITE/USDT", "n": 3})
        body = recent.json()
        assert body["view"] == "live"
        assert body["n"] == 3

        root = await client.get("/v1/snapshots/root", params={"asset": "KITE/USDT", "n": 3})
        rbody = root.json()
        assert rbody["view"] == "live"
        # The mirror's fake root must not leak through when we fell back.
        assert int(rbody["root"]) != 0xDEAD


# --- Commit-on-demand: liveness validator + /anchor/commit endpoint -----


def test_anchor_liveness_validator_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORACLE_ANCHOR_LIVENESS_SEC", "170")
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]
    monkeypatch.setenv("ORACLE_ANCHOR_LIVENESS_SEC", "0")
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]
    monkeypatch.setenv("ORACLE_ANCHOR_LIVENESS_SEC", "150")
    assert Settings().anchor_liveness_sec == 150  # type: ignore[call-arg]
    monkeypatch.setenv("ORACLE_YIELD_ANCHOR_HEARTBEAT_SEC", "0")
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_build_app_wires_liveness_into_schedulers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORACLE_ANCHOR_LIVENESS_SEC", "90")
    monkeypatch.setenv("ORACLE_YIELD_ANCHOR_HEARTBEAT_SEC", "1800")
    app = build_app(Settings())  # type: ignore[call-arg]
    assert app.state.price_anchor_scheduler.liveness_sec == 90
    assert app.state.yield_anchor_scheduler.liveness_sec == 1800


@pytest.mark.asyncio
async def test_anchor_commit_endpoint_disabled_when_token_unset() -> None:
    app = build_app(Settings())  # type: ignore[call-arg]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/v1/anchor/commit", params={"asset": "KITE/USDT"})
        assert r.status_code == 503
        assert "disabled" in r.json()["detail"]


@pytest.mark.asyncio
async def test_anchor_commit_endpoint_auth_and_safe_degradation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORACLE_ANCHOR_COMMIT_TOKEN", "s3cret")
    app = build_app(Settings())  # type: ignore[call-arg]
    poller = app.state.poller
    for _ in range(3):
        await poller.tick_once()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Missing token → 401.
        missing = await client.post("/v1/anchor/commit", params={"asset": "KITE/USDT"})
        assert missing.status_code == 401
        # Wrong token → 401.
        wrong = await client.post(
            "/v1/anchor/commit",
            params={"asset": "KITE/USDT"},
            headers={"Authorization": "Bearer nope"},
        )
        assert wrong.status_code == 401
        # Correct token, asset tracked, window present — but scenario mode
        # has no anchor address so the poster is dry-run (not mined). The
        # endpoint must 503 so the strategy skips rather than submitting a
        # doomed proof (strictly safer than today's on-chain revert).
        ok = await client.post(
            "/v1/anchor/commit",
            params={"asset": "KITE/USDT"},
            headers={"Authorization": "Bearer s3cret"},
        )
        assert ok.status_code == 503
        assert "not mined" in ok.json()["detail"]
        # Unknown asset → 404 (after auth).
        nf = await client.post(
            "/v1/anchor/commit",
            params={"asset": "DOGE/USDT"},
            headers={"Authorization": "Bearer s3cret"},
        )
        assert nf.status_code == 404
