"""Service integration: REST endpoints + WebSocket fanout via stubbed engine."""

from __future__ import annotations

import os

import httpx
import pytest
from reputation.goldsky import AllocatorState, NavEvent, StrategyState, TradeEvent
from reputation.service import Settings, build_app
from reputation.windows import DAY_SEC

_NOW = 1_700_000_000


class _StubGoldsky:
    def __init__(self, states: list[StrategyState]) -> None:
        self._states = states

    async def fetch_strategy_states(self, since_unix: int) -> list[StrategyState]:
        return list(self._states)

    async def aclose(self) -> None:
        return None


def _state(strategy_id: str, declared_class: str = "0x" + "ab" * 32) -> StrategyState:
    return StrategyState(
        strategy_id=strategy_id,
        declared_class=declared_class,
        stake_e18=5_000 * 10**18,
        trades_attested=100,
        capital_deployed_e18=10**18,
        trades_90d=[
            TradeEvent(timestamp=_NOW - d * DAY_SEC, proof_valid=True, amount_in_e18=10**18)
            for d in (1, 5, 10)
        ],
        nav_snapshots_90d=[
            NavEvent(
                timestamp=_NOW - d * DAY_SEC,
                total_nav_e18=int(10**18 * (1 + 0.001 * (10 - d))),
            )
            for d in range(10, 0, -1)
        ],
    )


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in list(os.environ):
        if k.startswith("REPUTATION_") or k in {"SCENARIO_MODE", "SCENARIO_FILE"}:
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("REPUTATION_SIGNER_PK", "0x" + "33" * 32)
    monkeypatch.setenv("REPUTATION_ANCHOR_ADDRESS", "0x" + "ab" * 20)


@pytest.mark.asyncio
async def test_scores_endpoints_after_one_tick() -> None:
    settings = Settings()  # type: ignore[call-arg]
    app = build_app(settings)
    engine = app.state.engine

    state = _state("0x" + "cd" * 20)
    engine._goldsky = _StubGoldsky([state])  # type: ignore[attr-defined]
    await engine.tick_once(now_unix=_NOW)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        recent = await client.get("/v1/scores/recent")
        assert recent.status_code == 200
        body = recent.json()
        assert body["count"] == 1
        score = body["scores"][0]
        assert isinstance(score["score_e4"], int)
        assert -10_000 <= score["score_e4"] <= 10_000
        assert score["components"].keys() == {"performance", "risk", "proof", "stake", "age"}
        assert score["components_hash"].startswith("0x") and len(score["components_hash"]) == 66
        assert (
            score["signed"]["signature"].startswith("0x")
            and len(score["signed"]["signature"]) == 132
        )
        # Whichever typehash the service is configured with should round-trip
        # through the API. Pinning to a literal made the test brittle to
        # `.env` files that pre-flip to v2.
        assert score["signed"]["typehash_version"] == settings.typehash_version

        one = await client.get(f"/v1/scores/{state.strategy_id}")
        assert one.status_code == 200
        assert one.json()["score_e4"] == score["score_e4"]

        missing = await client.get("/v1/scores/0xdead")
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_audit_endpoint_returns_full_breakdown() -> None:
    settings = Settings()  # type: ignore[call-arg]
    app = build_app(settings)
    engine = app.state.engine

    state = _state("0x" + "cd" * 20)
    engine._goldsky = _StubGoldsky([state])  # type: ignore[attr-defined]
    await engine.tick_once(now_unix=_NOW)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/v1/audit/{state.strategy_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["actor"] == state.strategy_id
        assert body["weights"] == {
            "performance": 0.40,
            "risk": 0.25,
            "proof": 0.15,
            "stake": 0.10,
            "age": 0.10,
        }
        assert {"win_7d", "win_30d", "win_90d"} == body["cohort"].keys()
        assert {"sharpe_7d", "sharpe_30d", "sharpe_90d", "norm_7d", "norm_30d", "norm_90d"} == (
            body["perf_breakdown"].keys()
        )
        # PR4: phase2-review.md item 17 — proof component is binary 0/1
        # in Phase 2, so the audit payload must carry the caveat.
        assert body["proof_score_is_binary"] is True

        missing = await client.get("/v1/audit/0xdead")
        assert missing.status_code == 404


class _StubAllocatorGoldsky:
    """Goldsky stub that satisfies both the strategy and allocator
    fetchers `ReputationEngine` consumes from `_run`."""

    def __init__(self, states: list[AllocatorState]) -> None:
        self._states = states

    async def fetch_strategy_states(self, since_unix: int) -> list[StrategyState]:
        return []

    async def fetch_allocator_states(self, window_start_unix: int) -> list[AllocatorState]:
        return list(self._states)

    async def aclose(self) -> None:
        return None


def _allocator_state(allocator_id: str) -> AllocatorState:
    """Mid-range allocator state — non-zero P&L, one breach handled,
    stable user count. Confirms the audit endpoint surfaces all four
    components without hitting the cold-start floor."""
    return AllocatorState(
        allocator_id=allocator_id,
        declared_class="momentum_v1",
        stake_e18=10_000 * 10**18,
        max_stake_in_class_e18=20_000 * 10**18,
        aggregate_pnl_above_hwm_e18=500 * 10**18,
        aggregate_capital_e18=100_000 * 10**18,
        breach_total_count=2,
        breach_response_count=2,
        users_at_window_start=10,
        users_at_window_end=11,
    )


@pytest.mark.asyncio
async def test_audit_endpoint_returns_allocator_breakdown() -> None:
    """WS5.A regression — the previous /v1/audit handler only read
    `engine.latest`, so any allocator that scored 404'd. The endpoint
    must now fall back to `engine.latest_allocators` and surface the
    four-component allocator shape."""
    settings = Settings()  # type: ignore[call-arg]
    app = build_app(settings)
    engine = app.state.engine

    allocator_id = "0x" + "ab" * 20
    engine._goldsky = _StubAllocatorGoldsky([_allocator_state(allocator_id)])  # type: ignore[attr-defined]
    await engine.tick_allocators_once(now_unix=_NOW)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/v1/audit/{allocator_id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["actor"] == allocator_id
        assert body["actorType"] == 1
        assert body["components"].keys() == {"pnl", "drawdown", "retention", "stake"}
        assert body["weights"] == {
            "pnl": 0.55,
            "drawdown": 0.20,
            "retention": 0.15,
            "stake": 0.10,
        }
        assert body["inputs"]["breach_total_count"] == 2
        assert body["inputs"]["breach_response_count"] == 2
        assert body["components_hash"].startswith("0x") and len(body["components_hash"]) == 66
