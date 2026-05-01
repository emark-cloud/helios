"""End-to-end engine: stub Goldsky → cohort → score → signed update → fanout.

Phase 2 (`Helios.md §8.2`). The engine pulls per-strategy state, builds class
cohorts, normalizes Sharpes per window, and signs the resulting score.
"""

from __future__ import annotations

import pytest
from reputation.engine import ReputationEngine
from reputation.goldsky import NavEvent, StrategyState, TradeEvent
from reputation.signer import ActorType, ReputationSigner
from reputation.windows import DAY_SEC

_NOW = 1_700_000_000


class _StubGoldsky:
    def __init__(self, states: list[StrategyState]) -> None:
        self._states = states
        self.last_since: int | None = None

    async def fetch_strategy_states(self, since_unix: int) -> list[StrategyState]:
        self.last_since = since_unix
        return list(self._states)

    async def aclose(self) -> None:  # pragma: no cover
        return None


@pytest.fixture()
def signer() -> ReputationSigner:
    return ReputationSigner("0x" + "22" * 32, chain_id=2368, anchor_address="0x" + "ab" * 20)


def _trending_navs(start_e18: int, daily_drift: float, days: int) -> list[NavEvent]:
    return [
        NavEvent(
            timestamp=_NOW - (days - 1 - d) * DAY_SEC,
            total_nav_e18=int(start_e18 * (1 + daily_drift) ** d),
        )
        for d in range(days)
    ]


def _trade(d_ago: int, valid: bool = True) -> TradeEvent:
    return TradeEvent(timestamp=_NOW - d_ago * DAY_SEC, proof_valid=valid, amount_in_e18=10**18)


def _state(
    strategy_id: str,
    declared_class: str = "0x" + "11" * 32,
    stake_e18: int = 5_000 * 10**18,
    trades_attested: int = 100,
    capital_deployed_e18: int = 10**18,
    nav_drift: float = 0.001,
    nav_days: int = 30,
) -> StrategyState:
    return StrategyState(
        strategy_id=strategy_id,
        declared_class=declared_class,
        stake_e18=stake_e18,
        trades_attested=trades_attested,
        capital_deployed_e18=capital_deployed_e18,
        trades_90d=[_trade(d) for d in range(0, nav_days, 3)],
        nav_snapshots_90d=_trending_navs(10**18, nav_drift, nav_days),
    )


@pytest.mark.asyncio
async def test_tick_signs_and_caches_latest(signer: ReputationSigner) -> None:
    state = _state(strategy_id="0x" + "cd" * 20)
    engine = ReputationEngine(_StubGoldsky([state]), signer, poll_interval_sec=60)  # type: ignore[arg-type]
    [u] = await engine.tick_once(now_unix=_NOW)

    assert u.signed.update.actor_type == ActorType.STRATEGY
    assert u.signed.update.last_update_block == _NOW
    assert u.signed.signature != b"\x00" * 65
    assert u.signed.typehash_version == "1"
    cached = engine.latest
    assert state.strategy_id in cached
    assert cached[state.strategy_id].outputs.score_e4 == u.outputs.score_e4


@pytest.mark.asyncio
async def test_subscribe_receives_updates(signer: ReputationSigner) -> None:
    state = _state(strategy_id="0x" + "cd" * 20)
    engine = ReputationEngine(_StubGoldsky([state]), signer, poll_interval_sec=60)  # type: ignore[arg-type]
    q = engine.subscribe()
    await engine.tick_once(now_unix=_NOW)
    received = await q.get()
    assert received.state.strategy_id == state.strategy_id


@pytest.mark.asyncio
async def test_ninety_day_window_used(signer: ReputationSigner) -> None:
    stub = _StubGoldsky([])
    engine = ReputationEngine(stub, signer, poll_interval_sec=60)  # type: ignore[arg-type]
    await engine.tick_once(now_unix=2_000_000_000)
    assert stub.last_since == 2_000_000_000 - 90 * 24 * 60 * 60


@pytest.mark.asyncio
async def test_cohort_normalizes_across_class(signer: ReputationSigner) -> None:
    """A class with three strategies — the stronger trender outscores the weaker.

    WS7.B requires `MIN_COHORT_SIZE = 3` for non-fallback cohort stats; with
    only two strategies in a class the engine falls back to raw Sharpe and
    both strong/weak trenders clip to `perf = 1.0`, hiding the cross-strategy
    ranking. Three peers is the smallest cohort that still produces a
    meaningful median + range.
    """
    cls = "0x" + "11" * 32
    strong = _state(strategy_id="0x" + "01" * 20, declared_class=cls, nav_drift=0.003)
    mid = _state(strategy_id="0x" + "03" * 20, declared_class=cls, nav_drift=0.0015)
    weak = _state(strategy_id="0x" + "02" * 20, declared_class=cls, nav_drift=0.0005)
    engine = ReputationEngine(_StubGoldsky([strong, mid, weak]), signer, poll_interval_sec=60)  # type: ignore[arg-type]
    updates = await engine.tick_once(now_unix=_NOW)
    by_id = {u.state.strategy_id: u for u in updates}
    assert by_id[strong.strategy_id].outputs.score_e4 > by_id[weak.strategy_id].outputs.score_e4
    # All three peers see the same cohort context object.
    assert (
        by_id[strong.strategy_id].cohort.win_30d.size
        == by_id[weak.strategy_id].cohort.win_30d.size
        == 3
    )


@pytest.mark.asyncio
async def test_singleton_class_falls_back_to_neutral_cohort(signer: ReputationSigner) -> None:
    only = _state(strategy_id="0x" + "ee" * 20, declared_class="0x" + "ff" * 32)
    engine = ReputationEngine(_StubGoldsky([only]), signer, poll_interval_sec=60)  # type: ignore[arg-type]
    [u] = await engine.tick_once(now_unix=_NOW)
    assert u.cohort.win_7d.is_fallback is True
    assert u.cohort.win_30d.is_fallback is True
    assert u.cohort.win_90d.is_fallback is True


@pytest.mark.asyncio
async def test_drawdown_extracted_from_nav_snapshots(signer: ReputationSigner) -> None:
    # Peak then trough: 1.0 → 1.5 → 0.9 → drawdown = (1.5 - 0.9) / 1.5 = 0.40 = 4000 bps
    snaps = [
        NavEvent(timestamp=_NOW - 4 * DAY_SEC, total_nav_e18=10**18),
        NavEvent(timestamp=_NOW - 3 * DAY_SEC, total_nav_e18=15 * 10**17),
        NavEvent(timestamp=_NOW - 1 * DAY_SEC, total_nav_e18=9 * 10**17),
    ]
    state = StrategyState(
        strategy_id="0x" + "dd" * 20,
        declared_class="0x" + "11" * 32,
        stake_e18=10**18,
        trades_attested=10,
        capital_deployed_e18=10**18,
        trades_90d=[_trade(1)],
        nav_snapshots_90d=snaps,
    )
    engine = ReputationEngine(_StubGoldsky([state]), signer, poll_interval_sec=60)  # type: ignore[arg-type]
    [u] = await engine.tick_once(now_unix=_NOW)
    assert u.inputs.max_drawdown_bps_90d == 4000


@pytest.mark.asyncio
async def test_components_hash_is_32_bytes_and_signed(signer: ReputationSigner) -> None:
    state = _state(strategy_id="0x" + "ab" * 20)
    engine = ReputationEngine(_StubGoldsky([state]), signer, poll_interval_sec=60)  # type: ignore[arg-type]
    [u] = await engine.tick_once(now_unix=_NOW)
    assert len(u.outputs.components_hash) == 32
    assert u.signed.update.components_hash == u.outputs.components_hash
