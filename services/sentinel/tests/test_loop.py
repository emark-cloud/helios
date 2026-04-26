"""End-to-end decision loop with stub Goldsky + dry-run on-chain runner."""

from __future__ import annotations

import pytest
from helios_allocator.types import MetaStrategy, StrategyCandidate
from sentinel.allocator import SentinelAllocator
from sentinel.goldsky import SentinelGoldsky
from sentinel.loop import LoopConfig, SentinelLoop
from sentinel.onchain import OnChainRunner
from sentinel.state import AllocationState, SentinelStore


class _StubGoldsky(SentinelGoldsky):
    """Returns canned candidates without HTTP."""

    def __init__(self, candidates: list[StrategyCandidate]) -> None:
        self._candidates_seed = candidates

    async def fetch_candidates(self) -> list[StrategyCandidate]:  # type: ignore[override]
        return list(self._candidates_seed)

    async def aclose(self) -> None:  # pragma: no cover
        return None


def _user_meta(
    *,
    drawdown_bps: int = 1_500,
    max_per_strategy_bps: int = 5_000,
    max_strategies_count: int = 2,
    rebalance_cadence_sec: int = 900,
) -> MetaStrategy:
    return MetaStrategy(
        user_address="0x" + "ab" * 20,
        allowed_strategy_classes=("momentum_v1",),
        allowed_assets=("USDC", "WKITE"),
        allowed_chains=(2368,),
        max_capital_usd=100_000,
        max_per_strategy_bps=max_per_strategy_bps,
        max_strategies_count=max_strategies_count,
        drawdown_threshold_bps=drawdown_bps,
        max_fee_rate_bps=2_500,
        rebalance_cadence_sec=rebalance_cadence_sec,
        valid_until=2_000_000_000,
    )


def _candidate(sid: str, *, rep: float = 0.8) -> StrategyCandidate:
    return StrategyCandidate(
        strategy_id=sid,
        declared_class="momentum_v1",
        chain_id=2368,
        operator="0x" + "cc" * 20,
        fee_rate_bps=1_000,
        stake_amount_usd=5_000,
        max_capacity_usd=100_000,
        current_allocations_usd=0,
        reputation_score=rep,
    )


def _build(
    candidates: list[StrategyCandidate], **cfg_overrides: int
) -> tuple[SentinelLoop, SentinelStore, OnChainRunner]:
    store = SentinelStore()
    allocator = SentinelAllocator()
    goldsky = _StubGoldsky(candidates)
    onchain = OnChainRunner(
        rpc_url="",
        operator_pk="",
        allocator_vault_address="",
        allocator_registry_address="",
        chain_id=2368,
    )
    cfg = LoopConfig(**cfg_overrides) if cfg_overrides else LoopConfig()
    loop = SentinelLoop(store, allocator, goldsky, onchain, config=cfg)
    return loop, store, onchain


@pytest.mark.asyncio
async def test_first_tick_allocates_idle_capital() -> None:
    s1 = _candidate("0x" + "11" * 20, rep=0.9)
    s2 = _candidate("0x" + "22" * 20, rep=0.5)
    loop, store, onchain = _build([s1, s2])

    user = store.upsert_user(_user_meta(max_per_strategy_bps=10_000))
    user.delegated_capital_usd = 10_000

    await loop.tick_once(now=1_000)

    methods = [c.method for c in onchain.pending]
    assert methods.count("allocateToStrategy") == 2
    by_strat = {c.strategy: c.amount for c in onchain.pending if c.method == "allocateToStrategy"}
    # Score-weighted: 0.9 / (0.9+0.5) ≈ 64.28% → ~6428 / 3571
    assert sum(by_strat.values()) <= 10_000
    assert by_strat[s1.strategy_id] > by_strat[s2.strategy_id]


@pytest.mark.asyncio
async def test_drawdown_breach_emits_defund() -> None:
    s1 = _candidate("0x" + "11" * 20)
    loop, store, onchain = _build([s1])

    user = store.upsert_user(_user_meta(drawdown_bps=1_500))
    user.delegated_capital_usd = 10_000
    user.allocations[s1.strategy_id] = AllocationState(
        strategy_id=s1.strategy_id,
        chain_id=2368,
        declared_class="momentum_v1",
        capital_deployed_usd=10_000,
        high_water_mark_usd=10_000,
        nav_usd=8_300,  # -17% drawdown, breaches 15% threshold
    )
    user.last_rebalance_ts = 1_000  # suppress rebalance pass; isolate drawdown

    await loop.tick_once(now=1_100)

    defunds = [c for c in onchain.pending if c.method == "defundStrategy"]
    assert len(defunds) == 1
    assert defunds[0].reason == "DRAWDOWN_BREACH"
    assert user.allocations[s1.strategy_id].defunded


@pytest.mark.asyncio
async def test_drawdown_under_threshold_does_not_defund() -> None:
    s1 = _candidate("0x" + "11" * 20)
    loop, store, onchain = _build([s1])

    user = store.upsert_user(_user_meta(drawdown_bps=1_500))
    user.delegated_capital_usd = 10_000
    user.allocations[s1.strategy_id] = AllocationState(
        strategy_id=s1.strategy_id,
        chain_id=2368,
        declared_class="momentum_v1",
        capital_deployed_usd=10_000,
        high_water_mark_usd=10_000,
        nav_usd=9_000,  # -10%, below threshold
    )
    user.last_rebalance_ts = 1_000

    await loop.tick_once(now=1_100)
    assert not any(c.method == "defundStrategy" for c in onchain.pending)
    assert not user.allocations[s1.strategy_id].defunded


@pytest.mark.asyncio
async def test_drawdown_takes_priority_over_rank_drop() -> None:
    """Even when a strategy also dropped out of the rank, the defund
    should be tagged DRAWDOWN_BREACH (the higher-priority reason)."""
    s1 = _candidate("0x" + "11" * 20)  # currently held, breaches drawdown
    s2 = _candidate("0x" + "22" * 20)  # the new winner
    loop, store, onchain = _build([s2])  # s1 not in candidate list — would rank-drop

    user = store.upsert_user(_user_meta(drawdown_bps=1_000))
    user.delegated_capital_usd = 10_000
    user.allocations[s1.strategy_id] = AllocationState(
        strategy_id=s1.strategy_id,
        chain_id=2368,
        declared_class="momentum_v1",
        capital_deployed_usd=10_000,
        high_water_mark_usd=10_000,
        nav_usd=8_500,  # -15%, breaches 10%
    )

    await loop.tick_once(now=1_000)

    # The defund tagged DRAWDOWN_BREACH must run before rank-diff converts
    # s1 into a "defund(RANK_DROP)" call. Drawdown enforcement marks it
    # defunded, so the rank-diff sees no active position to remove.
    defunds = [c for c in onchain.pending if c.method == "defundStrategy"]
    reasons = [c.reason for c in defunds if c.strategy == s1.strategy_id]
    assert "DRAWDOWN_BREACH" in reasons


@pytest.mark.asyncio
async def test_fee_settled_when_nav_above_threshold() -> None:
    s1 = _candidate("0x" + "11" * 20)
    loop, store, onchain = _build([s1])

    user = store.upsert_user(_user_meta())
    user.delegated_capital_usd = 10_000
    user.allocations[s1.strategy_id] = AllocationState(
        strategy_id=s1.strategy_id,
        chain_id=2368,
        declared_class="momentum_v1",
        capital_deployed_usd=10_000,
        high_water_mark_usd=10_000,
        nav_usd=10_700,  # +7%, above 5% fee threshold
    )
    user.last_rebalance_ts = 1_000

    await loop.tick_once(now=1_500)

    fees = [c for c in onchain.pending if c.method == "settleStrategyFee"]
    assert len(fees) == 1
    # HWM bumped to current NAV.
    assert user.allocations[s1.strategy_id].high_water_mark_usd == 10_700


@pytest.mark.asyncio
async def test_rebalance_skipped_within_cadence() -> None:
    s1 = _candidate("0x" + "11" * 20)
    loop, store, onchain = _build([s1])

    user = store.upsert_user(_user_meta(rebalance_cadence_sec=900))
    user.delegated_capital_usd = 10_000
    user.last_rebalance_ts = 1_000

    await loop.tick_once(now=1_100)  # 100s elapsed, well below 900s cadence
    assert not any(c.method == "allocateToStrategy" for c in onchain.pending)


@pytest.mark.asyncio
async def test_event_fanout_to_subscriber() -> None:
    s1 = _candidate("0x" + "11" * 20)
    loop, store, _ = _build([s1])
    user = store.upsert_user(_user_meta())
    user.delegated_capital_usd = 10_000

    q = store.subscribe(user.meta.user_address)
    await loop.tick_once(now=1_000)

    assert not q.empty()
    drained = []
    while not q.empty():
        drained.append(q.get_nowait())
    kinds = [e.kind for e in drained]
    assert "ALLOCATION_CREATED" in kinds
    assert "REBALANCE_COMPLETE" in kinds
