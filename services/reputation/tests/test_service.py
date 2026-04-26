"""Service integration: REST endpoints + WebSocket fanout via stubbed engine."""

from __future__ import annotations

import os

import httpx
import pytest
from reputation.goldsky import StrategyRollup
from reputation.service import Settings, build_app


class _StubGoldsky:
    def __init__(self, rollups: list[StrategyRollup]) -> None:
        self._rollups = rollups

    async def fetch_strategy_rollups(self, since_unix: int) -> list[StrategyRollup]:
        return list(self._rollups)

    async def aclose(self) -> None:
        return None


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

    rollup = StrategyRollup(
        strategy_id="0x" + "cd" * 20,
        declared_class="0xabcd",
        total_attested_trades=5,
        total_proof_valid=5,
        capital_deployed_e18=10**18,
        realized_pnl_30d_e18=10**17,  # +10% return → 0.7 × 0.1 + 0.3 = 0.37 → 3700
    )
    # Swap goldsky on the running engine.
    engine._goldsky = _StubGoldsky([rollup])  # type: ignore[attr-defined]
    await engine.tick_once(now_unix=1_700_000_000)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        recent = await client.get("/v1/scores/recent")
        assert recent.status_code == 200
        body = recent.json()
        assert body["count"] == 1
        score = body["scores"][0]
        assert score["score_e4"] == 3700
        assert score["signed"]["currentScore"] == 3700
        assert (
            score["signed"]["signature"].startswith("0x")
            and len(score["signed"]["signature"]) == 132
        )

        one = await client.get(f"/v1/scores/{rollup.strategy_id}")
        assert one.status_code == 200
        assert one.json()["score_e4"] == 3700

        missing = await client.get("/v1/scores/0xdead")
        assert missing.status_code == 404
