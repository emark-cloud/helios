"""WS5.A — Allocator reputation engine branch.

Synthetic ledger tests covering the four-factor formula
(0.55·P&L / 0.20·drawdown / 0.15·retention / 0.10·stake) plus the
cold-start floor (zero users → stake-only).
"""

from __future__ import annotations

import pytest
from reputation.engine import ReputationEngine
from reputation.goldsky import AllocatorState
from reputation.signer import ActorType, ReputationSigner

_NOW = 1_700_000_000
_CLASS = "0x" + "11" * 32


class _StubGoldsky:
    def __init__(self, allocators: list[AllocatorState]) -> None:
        self._allocators = allocators
        self.last_window_start: int | None = None

    async def fetch_strategy_states(self, since_unix: int) -> list[object]:
        del since_unix
        return []

    async def fetch_allocator_states(self, window_start_unix: int) -> list[AllocatorState]:
        self.last_window_start = window_start_unix
        return list(self._allocators)

    async def aclose(self) -> None:  # pragma: no cover
        return None


@pytest.fixture()
def signer() -> ReputationSigner:
    return ReputationSigner("0x" + "44" * 32, chain_id=2368, anchor_address="0x" + "ab" * 20)


def _alloc(
    allocator_id: str,
    *,
    stake_e18: int = 5_000 * 10**18,
    max_stake_e18: int = 10_000 * 10**18,
    pnl_e18: int = 0,
    capital_e18: int = 100 * 10**18,
    breaches: int = 0,
    breach_responses: int = 0,
    users_start: int = 3,
    users_end: int = 3,
) -> AllocatorState:
    return AllocatorState(
        allocator_id=allocator_id,
        declared_class=_CLASS,
        stake_e18=stake_e18,
        max_stake_in_class_e18=max_stake_e18,
        aggregate_pnl_above_hwm_e18=pnl_e18,
        aggregate_capital_e18=capital_e18,
        breach_total_count=breaches,
        breach_response_count=breach_responses,
        users_at_window_start=users_start,
        users_at_window_end=users_end,
    )


@pytest.mark.asyncio
async def test_tick_signs_with_allocator_actor_type(signer: ReputationSigner) -> None:
    state = _alloc("0x" + "aa" * 20)
    engine = ReputationEngine(_StubGoldsky([state]), signer, poll_interval_sec=60)  # type: ignore[arg-type]
    [u] = await engine.tick_allocators_once(now_unix=_NOW)

    assert u.signed.update.actor_type == ActorType.ALLOCATOR
    assert u.signed.update.actor == state.allocator_id
    assert u.signed.update.last_update_block == _NOW
    assert u.signed.signature != b"\x00" * 65
    assert len(u.outputs.components_hash) == 32
    assert u.signed.update.components_hash == u.outputs.components_hash


@pytest.mark.asyncio
async def test_thirty_day_window_used(signer: ReputationSigner) -> None:
    stub = _StubGoldsky([])
    engine = ReputationEngine(stub, signer, poll_interval_sec=60)  # type: ignore[arg-type]
    await engine.tick_allocators_once(now_unix=2_000_000_000)
    assert stub.last_window_start == 2_000_000_000 - 30 * 24 * 60 * 60


@pytest.mark.asyncio
async def test_a_outscores_b_synthetic_ledger(signer: ReputationSigner) -> None:
    """Allocator A: 3 profitable users, all breaches handled fast.
    Allocator B: 3 mixed-P&L users, slow breach response, churn.

    Same stake → A's P&L + drawdown + retention components dominate."""
    a = _alloc(
        "0x" + "01" * 20,
        pnl_e18=8 * 10**18,  # +8 / 100 capital = +8%
        capital_e18=100 * 10**18,
        breaches=2,
        breach_responses=2,
        users_start=3,
        users_end=3,
    )
    b = _alloc(
        "0x" + "02" * 20,
        pnl_e18=-2 * 10**18,  # -2 / 100 capital = -2%
        capital_e18=100 * 10**18,
        breaches=4,
        breach_responses=1,
        users_start=3,
        users_end=2,
    )
    engine = ReputationEngine(_StubGoldsky([a, b]), signer, poll_interval_sec=60)  # type: ignore[arg-type]
    updates = await engine.tick_allocators_once(now_unix=_NOW)
    by_id = {u.state.allocator_id: u for u in updates}
    score_a = by_id[a.allocator_id].outputs.score_e4
    score_b = by_id[b.allocator_id].outputs.score_e4
    assert score_a > score_b, f"expected A > B; got {score_a} vs {score_b}"

    # Each component reflects the input divergence in the spec'd
    # direction: A pos pnl, A perfect drawdown, A perfect retention.
    ca = by_id[a.allocator_id].outputs.components
    cb = by_id[b.allocator_id].outputs.components
    assert ca.pnl > cb.pnl
    assert ca.drawdown > cb.drawdown
    assert ca.retention > cb.retention
    assert ca.stake == pytest.approx(cb.stake)  # equal stake


@pytest.mark.asyncio
async def test_cold_start_returns_stake_only_floor(signer: ReputationSigner) -> None:
    """An allocator with no users + no breaches scores against the
    stake-only floor (`w_stake · StakeScore`), parallel to §8.7."""
    fresh = _alloc(
        "0x" + "ee" * 20,
        stake_e18=2_000 * 10**18,
        max_stake_e18=10_000 * 10**18,
        users_start=0,
        users_end=0,
        breaches=0,
        breach_responses=0,
        pnl_e18=0,
        capital_e18=0,
    )
    engine = ReputationEngine(_StubGoldsky([fresh]), signer, poll_interval_sec=60)  # type: ignore[arg-type]
    [u] = await engine.tick_allocators_once(now_unix=_NOW)

    # Performance / drawdown / retention all zeroed in the floor branch.
    assert u.outputs.components.pnl == 0.0
    assert u.outputs.components.drawdown == 0.0
    assert u.outputs.components.retention == 0.0
    # Stake is non-zero (positive stake, positive class max).
    assert u.outputs.components.stake > 0.0
    # Score equals 10_000 × W_STAKE × stake → bounded by 10_000 × 0.10.
    assert 0 < u.outputs.score_e4 <= 1_000


@pytest.mark.asyncio
async def test_breach_discipline_rewards_fast_response(signer: ReputationSigner) -> None:
    """Equal P&L + retention + stake; only breach-response ratio differs.
    The faster responder scores higher."""
    fast = _alloc("0x" + "f1" * 20, breaches=4, breach_responses=4)
    slow = _alloc("0x" + "f2" * 20, breaches=4, breach_responses=1)
    engine = ReputationEngine(_StubGoldsky([fast, slow]), signer, poll_interval_sec=60)  # type: ignore[arg-type]
    updates = await engine.tick_allocators_once(now_unix=_NOW)
    by_id = {u.state.allocator_id: u for u in updates}
    assert by_id[fast.allocator_id].outputs.score_e4 > by_id[slow.allocator_id].outputs.score_e4


@pytest.mark.asyncio
async def test_retention_penalizes_churn(signer: ReputationSigner) -> None:
    """Equal everything except 30d retention. The retainer scores higher."""
    keeper = _alloc("0x" + "11" * 20, users_start=5, users_end=5)
    leaker = _alloc("0x" + "22" * 20, users_start=5, users_end=2)
    engine = ReputationEngine(_StubGoldsky([keeper, leaker]), signer, poll_interval_sec=60)  # type: ignore[arg-type]
    updates = await engine.tick_allocators_once(now_unix=_NOW)
    by_id = {u.state.allocator_id: u for u in updates}
    assert by_id[keeper.allocator_id].outputs.score_e4 > by_id[leaker.allocator_id].outputs.score_e4


@pytest.mark.asyncio
async def test_latest_allocators_caches_per_actor(signer: ReputationSigner) -> None:
    a = _alloc("0x" + "01" * 20, pnl_e18=5 * 10**18)
    b = _alloc("0x" + "02" * 20, pnl_e18=-5 * 10**18)
    engine = ReputationEngine(_StubGoldsky([a, b]), signer, poll_interval_sec=60)  # type: ignore[arg-type]
    await engine.tick_allocators_once(now_unix=_NOW)
    cached = engine.latest_allocators
    assert set(cached) == {a.allocator_id, b.allocator_id}
    assert cached[a.allocator_id].outputs.score_e4 != cached[b.allocator_id].outputs.score_e4


@pytest.mark.asyncio
async def test_stale_goldsky_without_allocator_method_no_ops(
    signer: ReputationSigner,
) -> None:
    """Strategy-only Goldsky stubs (e.g. existing test_engine fixtures)
    don't implement `fetch_allocator_states`. The engine should silently
    no-op rather than break the strategy path."""

    class _StrategyOnlyStub:
        async def fetch_strategy_states(self, since_unix: int) -> list[object]:
            del since_unix
            return []

        async def aclose(self) -> None:  # pragma: no cover
            return None

    engine = ReputationEngine(_StrategyOnlyStub(), signer, poll_interval_sec=60)  # type: ignore[arg-type]
    updates = await engine.tick_allocators_once(now_unix=_NOW)
    assert updates == []
