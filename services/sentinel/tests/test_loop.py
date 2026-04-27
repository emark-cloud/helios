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
async def test_full_scenario_allocate_drawdown_reallocate() -> None:
    """Phase 1 acceptance scenario: user delegates capital → Sentinel
    splits across two strategies → one breaches drawdown next tick →
    Sentinel defunds the loser and redeploys the freed budget into
    the survivor in the same tick."""
    s1 = _candidate("0x" + "11" * 20, rep=0.9)
    s2 = _candidate("0x" + "22" * 20, rep=0.5)

    store = SentinelStore()
    allocator = SentinelAllocator()
    onchain = OnChainRunner(
        rpc_url="",
        operator_pk="",
        allocator_vault_address="",
        allocator_registry_address="",
        chain_id=2368,
    )

    class _DynamicGoldsky(SentinelGoldsky):
        def __init__(self) -> None:
            self.calls = 0

        async def fetch_candidates(self) -> list[StrategyCandidate]:  # type: ignore[override]
            self.calls += 1
            # Tick 1: both active. Tick 2+: s2 has dropped from the
            # directory (subgraph reflects its losing streak).
            return [s1, s2] if self.calls == 1 else [s1]

        async def aclose(self) -> None:
            return None

    goldsky = _DynamicGoldsky()
    loop = SentinelLoop(
        store, allocator, goldsky, onchain, config=LoopConfig(rank_update_interval_sec=300)
    )

    user = store.upsert_user(
        _user_meta(
            drawdown_bps=1_500,
            max_per_strategy_bps=10_000,
            max_strategies_count=2,
            rebalance_cadence_sec=900,
        )
    )
    user.delegated_capital_usd = 10_000

    q = store.subscribe(user.meta.user_address)

    # ── Tick 1 (t=1_000): idle capital → two-strategy split ─────
    await loop.tick_once(now=1_000)

    initial_allocs = [c for c in onchain.pending if c.method == "allocateToStrategy"]
    assert len(initial_allocs) == 2
    s1_initial = next(c.amount for c in initial_allocs if c.strategy == s1.strategy_id)
    s2_initial = next(c.amount for c in initial_allocs if c.strategy == s2.strategy_id)
    assert s1_initial + s2_initial <= 10_000
    assert s1_initial > s2_initial  # higher-rep strategy gets the larger slice

    # Simulate market action between ticks: s2 craters, s1 holds.
    user.allocations[s2.strategy_id].nav_usd = int(s2_initial * 0.80)  # -20% > 15% threshold
    user.allocations[s1.strategy_id].nav_usd = s1_initial  # flat — no drawdown

    # ── Tick 2 (t=2_000): drawdown defund + reallocation ────────
    pre_pending = len(onchain.pending)
    await loop.tick_once(now=2_000)
    new_calls = onchain.pending[pre_pending:]

    defunds = [c for c in new_calls if c.method == "defundStrategy"]
    assert len(defunds) == 1
    assert defunds[0].strategy == s2.strategy_id
    assert defunds[0].reason == "DRAWDOWN_BREACH"
    assert user.allocations[s2.strategy_id].defunded

    # The freed budget redeploys into s1 — the only surviving candidate.
    increases = [
        c for c in new_calls if c.method == "allocateToStrategy" and c.strategy == s1.strategy_id
    ]
    assert len(increases) == 1
    # Target for s1 is full capital (only candidate, max_per_strategy=100%);
    # diff is target - current_active = 10_000 - s1_initial.
    assert increases[0].amount == 10_000 - s1_initial
    assert user.allocations[s1.strategy_id].capital_deployed_usd == 10_000
    assert user.last_rebalance_ts == 2_000

    # Event stream observed all three lifecycle events in order.
    drained = []
    while not q.empty():
        drained.append(q.get_nowait())
    kinds = [e.kind for e in drained]
    assert kinds.count("ALLOCATION_CREATED") == 2  # tick 1
    assert "STRATEGY_DEFUNDED" in kinds  # tick 2
    assert kinds.count("ALLOCATION_INCREASED") == 1  # tick 2 reallocation
    # Defund must be emitted before the reallocation event (drawdown step
    # runs before the rebalance step inside _tick_user).
    defund_idx = next(i for i, e in enumerate(drained) if e.kind == "STRATEGY_DEFUNDED")
    realloc_idx = next(i for i, e in enumerate(drained) if e.kind == "ALLOCATION_INCREASED")
    assert defund_idx < realloc_idx


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
