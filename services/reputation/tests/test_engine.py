"""End-to-end engine: stub Goldsky → score → signed update → fanout."""

from __future__ import annotations

import pytest
from reputation.engine import ReputationEngine
from reputation.goldsky import StrategyRollup
from reputation.signer import ActorType, ReputationSigner


class _StubGoldsky:
    """Returns canned StrategyRollups, no HTTP."""

    def __init__(self, rollups: list[StrategyRollup]) -> None:
        self._rollups = rollups
        self.last_since: int | None = None

    async def fetch_strategy_rollups(self, since_unix: int) -> list[StrategyRollup]:
        self.last_since = since_unix
        return list(self._rollups)

    async def aclose(self) -> None:  # pragma: no cover
        return None


@pytest.fixture()
def signer() -> ReputationSigner:
    return ReputationSigner("0x" + "22" * 32, chain_id=2368, anchor_address="0x" + "ab" * 20)


@pytest.mark.asyncio
async def test_tick_signs_and_caches_latest(signer: ReputationSigner) -> None:
    rollup = StrategyRollup(
        strategy_id="0x" + "cd" * 20,
        declared_class="0x1234",
        total_attested_trades=10,
        total_proof_valid=10,
        capital_deployed_e18=10**18,
        realized_pnl_30d_e18=2 * 10**17,  # +20% return
    )
    engine = ReputationEngine(_StubGoldsky([rollup]), signer, poll_interval_sec=60)  # type: ignore[arg-type]

    updates = await engine.tick_once(now_unix=1_700_000_000)
    assert len(updates) == 1
    u = updates[0]

    # 0.7 × 0.2 + 0.3 × 1 = 0.44 → 4400
    assert u.outputs.score_e4 == 4400
    assert u.signed.update.actor_type == ActorType.STRATEGY
    assert u.signed.update.last_update_block == 1_700_000_000
    assert u.signed.signature != b"\x00" * 65  # real signature

    cached = engine.latest
    assert rollup.strategy_id in cached
    assert cached[rollup.strategy_id].outputs.score_e4 == 4400


@pytest.mark.asyncio
async def test_subscribe_receives_updates(signer: ReputationSigner) -> None:
    rollup = StrategyRollup(
        strategy_id="0x" + "cd" * 20,
        declared_class="0x1234",
        total_attested_trades=1,
        total_proof_valid=1,
        capital_deployed_e18=10**18,
        realized_pnl_30d_e18=0,
    )
    engine = ReputationEngine(_StubGoldsky([rollup]), signer, poll_interval_sec=60)  # type: ignore[arg-type]
    q = engine.subscribe()
    await engine.tick_once(now_unix=1_700_000_000)
    assert not q.empty()
    received = await q.get()
    assert received.rollup.strategy_id == rollup.strategy_id


@pytest.mark.asyncio
async def test_thirty_day_window_used(signer: ReputationSigner) -> None:
    stub = _StubGoldsky([])
    engine = ReputationEngine(stub, signer, poll_interval_sec=60)  # type: ignore[arg-type]
    await engine.tick_once(now_unix=2_000_000_000)
    assert stub.last_since == 2_000_000_000 - 30 * 24 * 60 * 60


@pytest.mark.asyncio
async def test_no_active_allocation_keeps_proof_term(signer: ReputationSigner) -> None:
    rollup = StrategyRollup(
        strategy_id="0x" + "ee" * 20,
        declared_class="0x1234",
        total_attested_trades=3,
        total_proof_valid=3,
        capital_deployed_e18=0,  # not currently allocated
        realized_pnl_30d_e18=10**18,  # ignored when notional == 0
    )
    engine = ReputationEngine(_StubGoldsky([rollup]), signer, poll_interval_sec=60)  # type: ignore[arg-type]
    [u] = await engine.tick_once(now_unix=1_700_000_000)
    assert u.outputs.pnl_term_e4 == 0
    assert u.outputs.proof_term_e4 == 3000
    assert u.outputs.score_e4 == 3000
