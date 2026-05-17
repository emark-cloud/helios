"""REST + WebSocket surface tests under FastAPI's TestClient.

Drawdown / fee math is covered in test_loop.py — these tests focus on
HTTP shape, payload validation, and WS event delivery.
"""

from __future__ import annotations

from typing import Any

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient
from helios_allocator.runtime import AllocationState, AllocatorEvent, StrategyDirectoryRow
from helios_allocator.types import MetaStrategy, StrategyCandidate
from sentinel.auth import canonical_digest, ws_subscribe_digest
from sentinel.schemas import MetaStrategyPayload
from sentinel.service import Settings, build_app
from starlette.websockets import WebSocketDisconnect as StarletteDisconnect

_TEST_PK = "0x" + "11" * 32
_TEST_USER = Account.from_key(_TEST_PK).address


def _ws_query(user: str, *, valid_until: int = 4_000_000_000, pk: str = _TEST_PK) -> str:
    """Sign the WS subscribe digest and return a `?valid_until=...&signature=...`
    query string. Tests use a far-future `valid_until` so wall-clock skew
    doesn't flake the run."""
    digest = ws_subscribe_digest(user, valid_until)
    sig = Account.sign_message(encode_defunct(text=digest), pk).signature.hex()
    return f"?valid_until={valid_until}&signature={sig}"


def _signed_payload(**overrides: Any) -> dict[str, Any]:
    """Build a meta-strategy POST body signed by `_TEST_PK`."""
    base: dict[str, Any] = {
        "user_address": _TEST_USER,
        "allowed_strategy_classes": ["momentum_v1"],
        "allowed_assets": ["USDC", "WKITE"],
        "allowed_chains": [2368],
        "max_capital_usd": 10_000,
        "max_per_strategy_bps": 5_000,
        "max_strategies_count": 2,
        "drawdown_threshold_bps": 1_500,
        "max_fee_rate_bps": 2_500,
        "rebalance_cadence_sec": 900,
        "valid_until": 2_000_000_000,
        "nonce": 1,
    }
    base.update(overrides)
    payload = MetaStrategyPayload.model_validate(base)
    digest = canonical_digest(payload)
    sig = Account.sign_message(encode_defunct(text=digest), _TEST_PK).signature.hex()
    return {**base, "signature": sig}


@pytest.fixture()
def app_client() -> tuple[object, TestClient]:
    settings = Settings(  # type: ignore[call-arg]
        goldsky_endpoint="",
        kite_chain_id=2368,
    )
    app = build_app(settings)
    client = TestClient(app)
    return app, client


def test_root_endpoint(app_client: tuple[object, TestClient]) -> None:
    _app, client = app_client
    with client:
        r = client.get("/v1/")
        assert r.status_code == 200
        body = r.json()
        assert body["service"] == "Helios Sentinel"
        assert body["fee_rate_bps"] == 400
        assert body["live_chain_io"] is False  # no SENTINEL_ALLOCATOR_VAULT_ADDRESS set


def test_cors_blocks_unknown_origin(app_client: tuple[object, TestClient]) -> None:
    """Default `CORS_ALLOWED_ORIGINS` is the local frontend only; an
    unknown browser origin must NOT receive an Access-Control-Allow-Origin
    header on a preflight."""
    _app, client = app_client
    r = client.options(
        "/v1/",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


def test_cors_allows_known_origin(app_client: tuple[object, TestClient]) -> None:
    _app, client = app_client
    r = client.options(
        "/v1/",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_post_meta_strategy_creates_user(app_client: tuple[object, TestClient]) -> None:
    app, client = app_client
    payload = _signed_payload()
    with client:
        r = client.post(f"/v1/users/{_TEST_USER}/meta-strategy", json=payload)
        assert r.status_code == 200, r.text
        assert r.json()["user"].lower() == _TEST_USER.lower()
        store = app.state.store  # type: ignore[attr-defined]
        assert store.get_user(_TEST_USER) is not None


def test_post_meta_strategy_rejects_unsigned_stub(
    app_client: tuple[object, TestClient],
) -> None:
    """EIP-191 hardening — server must verify, not just store."""
    _app, client = app_client
    payload = _signed_payload()
    payload["signature"] = "0x"
    with client:
        r = client.post(f"/v1/users/{_TEST_USER}/meta-strategy", json=payload)
        assert r.status_code == 401
        assert "missing" in r.json()["detail"]


def test_post_meta_strategy_rejects_tampered_body(
    app_client: tuple[object, TestClient],
) -> None:
    _app, client = app_client
    payload = _signed_payload()
    payload["max_capital_usd"] = 999_999  # bumped after signing
    with client:
        r = client.post(f"/v1/users/{_TEST_USER}/meta-strategy", json=payload)
        assert r.status_code == 401
        assert "does not match" in r.json()["detail"]


def test_post_meta_strategy_rejects_path_body_mismatch(
    app_client: tuple[object, TestClient],
) -> None:
    _app, client = app_client
    # Signature is irrelevant — path/body mismatch is a 400 *before* we verify.
    payload = _signed_payload()
    with client:
        r = client.post(f"/v1/users/{'0x' + 'cd' * 20}/meta-strategy", json=payload)
        assert r.status_code == 400


def test_dashboard_404_for_unknown_user(app_client: tuple[object, TestClient]) -> None:
    _app, client = app_client
    with client:
        r = client.get(f"/v1/users/{'0x' + '99' * 20}/dashboard")
        assert r.status_code == 404


def test_dashboard_rehydrates_user_from_chain_on_store_miss(
    app_client: tuple[object, TestClient],
) -> None:
    """A Sentinel restart wipes the in-process store, but the on-chain
    UserVault still holds the user's signed meta + delegation. The
    dashboard must rebuild from chain (no re-signature) rather than
    404'ing a still-live delegation, and re-arm the allocator loop by
    landing the user back in the store.
    """
    app, client = app_client
    user_addr = "0x" + "5e" * 20

    async def _fake_read(u: str) -> MetaStrategy:
        return MetaStrategy(
            user_address=u,
            allowed_strategy_classes=["momentum_v1"],
            allowed_assets=[],
            allowed_chains=[2368],
            max_capital_usd=2_000,
            max_per_strategy_bps=3_500,
            max_strategies_count=5,
            drawdown_threshold_bps=1_500,
            max_fee_rate_bps=500,
            rebalance_cadence_sec=1_800,
            valid_until=9_999_999_999,
        )

    app.state.onchain.read_user_meta_strategy_async = _fake_read  # type: ignore[attr-defined]
    with client:
        store = app.state.store  # type: ignore[attr-defined]
        assert store.get_user(user_addr) is None  # wiped / never in store
        r = client.get(f"/v1/users/{user_addr}/dashboard")
        assert r.status_code == 200, r.text
        # User is now back in the store → the allocator loop will manage
        # them again on its next tick.
        assert store.get_user(user_addr) is not None


def test_dashboard_rehydrate_reconstructs_allocations_from_chain(
    app_client: tuple[object, TestClient],
) -> None:
    """Restoring the meta tells us *what* the user authorized but not
    *where their capital is*. The rehydrate path must also rebuild the
    live positions from `AllocatorVault.allocationOf`, so the dashboard
    shows real principal on the first post-restart hit instead of $0
    until the next cadence rebalance (the live 0xF235F71… symptom).
    """
    app, client = app_client
    user_addr = "0x" + "7a" * 20
    strat = "0x" + "11" * 20

    async def _fake_meta(u: str) -> MetaStrategy:
        return MetaStrategy(
            user_address=u,
            allowed_strategy_classes=["momentum_v1"],
            allowed_assets=[],
            allowed_chains=[2368],
            max_capital_usd=2_000,
            max_per_strategy_bps=3_500,
            max_strategies_count=5,
            drawdown_threshold_bps=1_500,
            max_fee_rate_bps=500,
            rebalance_cadence_sec=1_800,
            valid_until=9_999_999_999,
        )

    async def _fake_directory() -> list[StrategyDirectoryRow]:
        return [
            StrategyDirectoryRow(
                strategy_id=strat,
                declared_class="momentum_v1",
                chain_id=2368,
                operator="0x" + "00" * 20,
                fee_rate_bps=100,
                stake_amount_usd=0,
                max_capacity_usd=0,
                current_allocations_usd=0,
                reputation_score_e4=0,
            )
        ]

    async def _fake_allocs(u: str, strategies: list[str]) -> list[AllocationState]:
        assert strategies == [strat]  # only the Kite-local row was queried
        return [
            AllocationState(
                strategy_id=strat,
                chain_id=2368,
                declared_class="",  # filled from the directory by the service
                capital_deployed_usd=999 * 10**18,
                high_water_mark_usd=999 * 10**18,
                nav_usd=999 * 10**18,
            )
        ]

    app.state.onchain.read_user_meta_strategy_async = _fake_meta  # type: ignore[attr-defined]
    app.state.onchain.read_user_allocations_async = _fake_allocs  # type: ignore[attr-defined]
    app.state.loop.directory = _fake_directory  # type: ignore[attr-defined]
    with client:
        store = app.state.store  # type: ignore[attr-defined]
        assert store.get_user(user_addr) is None
        r = client.get(f"/v1/users/{user_addr}/dashboard")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total_capital_usd"] == 999  # not 0
        assert len(body["allocations"]) == 1
        row = body["allocations"][0]
        assert row["strategy_id"] == strat
        assert row["declared_class"] == "momentum_v1"  # backfilled from directory
        assert row["capital_deployed_usd"] == 999


def test_dashboard_returns_allocations(app_client: tuple[object, TestClient]) -> None:
    app, client = app_client
    user_addr = _TEST_USER
    with client:
        client.post(
            f"/v1/users/{user_addr}/meta-strategy",
            json=_signed_payload(allowed_assets=["USDC"]),
        )
        store = app.state.store  # type: ignore[attr-defined]
        store.update_allocation(
            user_addr,
            AllocationState(
                strategy_id="0x" + "11" * 20,
                chain_id=2368,
                declared_class="momentum_v1",
                capital_deployed_usd=5_000,
                high_water_mark_usd=5_000,
                nav_usd=4_900,
            ),
        )
        r = client.get(f"/v1/users/{user_addr}/dashboard")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["allocator_name"] == "Helios Sentinel"
        assert len(body["allocations"]) == 1
        assert body["allocations"][0]["drawdown_bps"] == 200  # (5000-4900)/5000 = 2%


def test_dashboard_scales_18dec_wei_to_usd(app_client: tuple[object, TestClient]) -> None:
    """Sentinel keeps every USD-named field as raw 18-dec base-asset units
    so the on-chain `allocateToStrategy(amount)` round-trip stays
    integer-clean. The dashboard surface is presentation-layer USD; the
    response payload divides by 10^18 so the frontend formatter can render
    `$33` instead of `$33,333,333,333,333,333,340,000`. Lock both directions
    so a future wei-vs-USD drift trips this test instead of shipping to
    the demo dashboard."""
    app, client = app_client
    user_addr = _TEST_USER
    with client:
        client.post(
            f"/v1/users/{user_addr}/meta-strategy",
            json=_signed_payload(allowed_assets=["USDC"]),
        )
        store = app.state.store  # type: ignore[attr-defined]
        store.update_allocation(
            user_addr,
            AllocationState(
                strategy_id="0x" + "11" * 20,
                chain_id=2368,
                declared_class="momentum_v1",
                capital_deployed_usd=33 * 10**18,  # 33 mUSDC in wei
                high_water_mark_usd=33 * 10**18,
                nav_usd=30 * 10**18,
            ),
        )
        r = client.get(f"/v1/users/{user_addr}/dashboard")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total_capital_usd"] == 33
        assert body["total_nav_usd"] == 30
        assert body["allocations"][0]["capital_deployed_usd"] == 33
        assert body["allocations"][0]["current_nav_usd"] == 30


def test_strategies_directory_filters_by_class(app_client: tuple[object, TestClient]) -> None:
    app, client = app_client

    async def fake_directory():
        return [
            StrategyDirectoryRow(
                strategy_id="0x" + "11" * 20,
                declared_class="momentum_v1",
                chain_id=2368,
                operator="0x" + "cc" * 20,
                fee_rate_bps=1_000,
                stake_amount_usd=5_000,
                max_capacity_usd=100_000,
                current_allocations_usd=0,
                reputation_score_e4=8_000,
            ),
            StrategyDirectoryRow(
                strategy_id="0x" + "22" * 20,
                declared_class="yield_rotation_v1",
                chain_id=2368,
                operator="0x" + "cc" * 20,
                fee_rate_bps=500,
                stake_amount_usd=5_000,
                max_capacity_usd=100_000,
                current_allocations_usd=0,
                reputation_score_e4=4_000,
            ),
        ]

    app.state.goldsky.fetch_directory = fake_directory  # type: ignore[attr-defined]

    with client:
        r = client.get("/v1/strategies?cls=momentum_v1")
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["declared_class"] == "momentum_v1"
        assert rows[0]["reputation_score"] == 0.8

        r2 = client.get("/v1/strategies?min_reputation=0.5")
        assert {row["strategy_id"] for row in r2.json()} == {"0x" + "11" * 20}


def test_websocket_streams_events(app_client: tuple[object, TestClient]) -> None:
    app, client = app_client
    user_addr = _TEST_USER
    with client:
        # Create user first so events route by address.
        client.post(
            f"/v1/users/{user_addr}/meta-strategy",
            json=_signed_payload(allowed_assets=["USDC"]),
        )
        store = app.state.store  # type: ignore[attr-defined]
        # Pre-emit a historical event so the replay path is exercised.
        store.emit_event(
            AllocatorEvent(
                user_address=user_addr,
                kind="ALLOCATION_CREATED",
                strategy_id="0x" + "11" * 20,
                amount_usd=5_000,
                reason="REBALANCE",
                timestamp=1_000,
            )
        )
        with client.websocket_connect(f"/v1/users/{user_addr}/events{_ws_query(user_addr)}") as ws:
            # The POST above also emits a META_STRATEGY_SET event so the
            # activity rail shows delegation on reconnect-replay; drain it
            # first, then assert on the manually pre-emitted ALLOCATION_CREATED.
            meta = ws.receive_json()
            assert meta["kind"] == "META_STRATEGY_SET"
            replayed = ws.receive_json()
            assert replayed["kind"] == "ALLOCATION_CREATED"
            assert replayed["strategy"] == "0x" + "11" * 20

            store.emit_event(
                AllocatorEvent(
                    user_address=user_addr,
                    kind="STRATEGY_DEFUNDED",
                    strategy_id="0x" + "11" * 20,
                    amount_usd=5_000,
                    reason="DRAWDOWN_BREACH",
                    timestamp=1_500,
                )
            )
            live = ws.receive_json()
            assert live["kind"] == "STRATEGY_DEFUNDED"
            assert live["reason"] == "DRAWDOWN_BREACH"


def test_websocket_rejects_unsigned_connection(
    app_client: tuple[object, TestClient],
) -> None:
    """HIGH #18 hardening — without a valid signature the server must
    close with code 4401 instead of streaming events."""
    _app, client = app_client
    with (
        client,
        pytest.raises(StarletteDisconnect) as info,
        client.websocket_connect(f"/v1/users/{_TEST_USER}/events"),
    ):
        pass
    assert info.value.code == 4401


def test_websocket_rejects_signature_for_other_user(
    app_client: tuple[object, TestClient],
) -> None:
    """A signature recovering to address A cannot subscribe to B's
    events stream — the recovered address must match the path user."""
    other_user = "0x" + "ab" * 20
    _app, client = app_client
    # `_ws_query` signs over `_TEST_USER`; targeting `other_user` mints
    # a fresh digest that the captured signature doesn't satisfy.
    qs = _ws_query(_TEST_USER)
    with (
        client,
        pytest.raises(StarletteDisconnect) as info,
        client.websocket_connect(f"/v1/users/{other_user}/events{qs}"),
    ):
        pass
    assert info.value.code == 4401


def test_websocket_rejects_expired_signature(
    app_client: tuple[object, TestClient],
) -> None:
    _app, client = app_client
    qs = _ws_query(_TEST_USER, valid_until=1)  # expired in 1970
    with (
        client,
        pytest.raises(StarletteDisconnect) as info,
        client.websocket_connect(f"/v1/users/{_TEST_USER}/events{qs}"),
    ):
        pass
    assert info.value.code == 4401


def test_candidate_caching_via_seed(app_client: tuple[object, TestClient]) -> None:
    """`AllocatorLoop.seed_candidates` is the test/scenario hook that lets
    the loop run without HTTP. Confirm it bypasses the rank-update gate."""
    app, _ = app_client
    loop = app.state.loop  # type: ignore[attr-defined]
    loop.seed_candidates(
        [
            StrategyCandidate(
                strategy_id="0x" + "11" * 20,
                declared_class="momentum_v1",
                chain_id=2368,
                operator="0x" + "cc" * 20,
                fee_rate_bps=1_000,
                stake_amount_usd=5_000,
                max_capacity_usd=100_000,
                current_allocations_usd=0,
                reputation_score=0.8,
            )
        ]
    )
    assert len(loop.candidates) == 1
