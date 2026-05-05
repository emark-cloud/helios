"""End-to-end decision loop with stub Goldsky + dry-run on-chain runner."""

from __future__ import annotations

import pytest
from helios_allocator.runtime import (
    AllocationState,
    AllocatorGoldsky,
    AllocatorLoop,
    AllocatorOnChain,
    AllocatorStore,
    LoopConfig,
    StrategyDirectoryRow,
)
from helios_allocator.types import MetaStrategy, StrategyCandidate
from sentinel.allocator import SentinelAllocator


def _candidate_to_row(c: StrategyCandidate) -> StrategyDirectoryRow:
    """PR5: loop now caches `StrategyDirectoryRow` so `/v1/strategies` can read
    from the same payload. Existing test fixtures still construct candidates;
    map them back to rows so the stub can satisfy `fetch_directory`."""
    return StrategyDirectoryRow(
        strategy_id=c.strategy_id,
        declared_class=c.declared_class,
        chain_id=c.chain_id,
        operator=c.operator,
        fee_rate_bps=c.fee_rate_bps,
        stake_amount_usd=c.stake_amount_usd,
        max_capacity_usd=c.max_capacity_usd,
        current_allocations_usd=c.current_allocations_usd,
        reputation_score_e4=round(c.reputation_score * 10_000),
        trades_attested=c.trades_attested,
    )


class _StubGoldsky(AllocatorGoldsky):
    """Returns canned candidates without HTTP."""

    def __init__(self, candidates: list[StrategyCandidate]) -> None:
        self._candidates_seed = candidates

    async def fetch_directory(self) -> list[StrategyDirectoryRow]:  # type: ignore[override]
        return [_candidate_to_row(c) for c in self._candidates_seed]

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


def _candidate(
    sid: str,
    *,
    rep: float = 0.8,
    trades_attested: int = 100,
    stake: int = 5_000,
) -> StrategyCandidate:
    # Default `trades_attested=100` keeps existing tests above the WS7.B
    # bootstrap-pool gate; cold-start tests opt in by passing 0.
    return StrategyCandidate(
        strategy_id=sid,
        declared_class="momentum_v1",
        chain_id=2368,
        operator="0x" + "cc" * 20,
        fee_rate_bps=1_000,
        stake_amount_usd=stake,
        max_capacity_usd=100_000,
        current_allocations_usd=0,
        reputation_score=rep,
        trades_attested=trades_attested,
    )


def _build(
    candidates: list[StrategyCandidate], **cfg_overrides: int
) -> tuple[AllocatorLoop, AllocatorStore, AllocatorOnChain]:
    store = AllocatorStore()
    allocator = SentinelAllocator()
    goldsky = _StubGoldsky(candidates)
    onchain = AllocatorOnChain(
        rpc_url="",
        operator_pk="",
        allocator_vault_address="",
        allocator_registry_address="",
        chain_id=2368,
    )
    cfg = LoopConfig(**cfg_overrides) if cfg_overrides else LoopConfig()
    loop = AllocatorLoop(store, allocator, goldsky, onchain, config=cfg)
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

    store = AllocatorStore()
    allocator = SentinelAllocator()
    onchain = AllocatorOnChain(
        rpc_url="",
        operator_pk="",
        allocator_vault_address="",
        allocator_registry_address="",
        chain_id=2368,
    )

    class _DynamicGoldsky(AllocatorGoldsky):
        def __init__(self) -> None:
            self.calls = 0

        async def fetch_directory(self) -> list[StrategyDirectoryRow]:  # type: ignore[override]
            self.calls += 1
            # Tick 1: both active. Tick 2+: s2 has dropped from the
            # directory (subgraph reflects its losing streak).
            cs = [s1, s2] if self.calls == 1 else [s1]
            return [_candidate_to_row(c) for c in cs]

        async def aclose(self) -> None:
            return None

    goldsky = _DynamicGoldsky()
    loop = AllocatorLoop(
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
async def test_cold_start_strategy_receives_bootstrap_allocation() -> None:
    """WS7.B acceptance: a brand-new strategy with zero attested trades and
    near-zero reputation still receives a bootstrap allocation through the
    Sentinel loop within one rebalance cycle, even when the user's main
    rank filter would exclude it.
    """
    veteran = _candidate("0x" + "11" * 20, rep=0.85, trades_attested=500)
    fresh = _candidate("0x" + "22" * 20, rep=0.0, trades_attested=0, stake=10_000)
    loop, store, onchain = _build([veteran, fresh])

    # bootstrap_share_bps=1000 (10%) is the SDK default — leave it alone.
    user = store.upsert_user(_user_meta(max_per_strategy_bps=10_000))
    user.delegated_capital_usd = 10_000

    await loop.tick_once(now=1_000)

    by_strat = {c.strategy: c.amount for c in onchain.pending if c.method == "allocateToStrategy"}
    # Both strategies funded — fresh one out of the bootstrap pool, veteran
    # out of the main pool.
    assert fresh.strategy_id in by_strat
    assert veteran.strategy_id in by_strat
    # 10% bootstrap of 10_000 = 1_000.
    assert by_strat[fresh.strategy_id] == 1_000
    # Veteran absorbs the remaining 9_000 (only main-pool candidate with
    # non-zero rank).
    assert by_strat[veteran.strategy_id] == 9_000


@pytest.mark.asyncio
async def test_partial_decrease_routes_through_rebalance() -> None:
    """Pure redistribution between two live strategies — score-weighted
    re-rank shifts capital from the loser to the winner. Phase 1 would
    defund the loser; the rebalance fast-path keeps both alive and
    issues a single `rebalance(weights_bps)` call.
    """
    # Same allowed_classes as default _candidate. Score swings sharply so
    # the new target meaningfully shifts capital while keeping both
    # strategies allocated.
    s1 = _candidate("0x" + "11" * 20, rep=0.5)
    s2 = _candidate("0x" + "22" * 20, rep=0.9)
    loop, store, onchain = _build([s1, s2])

    user = store.upsert_user(_user_meta(max_per_strategy_bps=10_000, max_strategies_count=2))
    user.delegated_capital_usd = 10_000
    # Seed prior allocation: 50/50 across both. Without the rebalance
    # fast-path the new target (~36/64) would defund s1 and re-allocate.
    user.allocations[s1.strategy_id] = AllocationState(
        strategy_id=s1.strategy_id,
        chain_id=2368,
        declared_class="momentum_v1",
        capital_deployed_usd=5_000,
        high_water_mark_usd=5_000,
        nav_usd=5_000,
    )
    user.allocations[s2.strategy_id] = AllocationState(
        strategy_id=s2.strategy_id,
        chain_id=2368,
        declared_class="momentum_v1",
        capital_deployed_usd=5_000,
        high_water_mark_usd=5_000,
        nav_usd=5_000,
    )
    user.last_rebalance_ts = 0  # eligible for rebalance pass

    await loop.tick_once(now=10_000)

    methods = [c.method for c in onchain.pending]
    assert "rebalance" in methods, methods
    assert "defundStrategy" not in methods
    rebs = [c for c in onchain.pending if c.method == "rebalance"]
    assert len(rebs) == 1
    # weights sum to 10_000 and the winner (s2) gets the larger share.
    assert sum(rebs[0].weights_bps) == 10_000
    assert (
        rebs[0].weights_bps[list(rebs[0].strategies).index(s2.strategy_id)]
        > rebs[0].weights_bps[list(rebs[0].strategies).index(s1.strategy_id)]
    )
    # In-memory state honours the new targets and neither is defunded.
    assert not user.allocations[s1.strategy_id].defunded
    assert not user.allocations[s2.strategy_id].defunded
    # Score-weighted allocator drops ≤1 USD per strategy as rounding
    # remainder, so the kept total is within tolerance of the seed.
    total = (
        user.allocations[s1.strategy_id].capital_deployed_usd
        + user.allocations[s2.strategy_id].capital_deployed_usd
    )
    assert 9_998 <= total <= 10_000
    # Winner ended up with the larger share.
    assert (
        user.allocations[s2.strategy_id].capital_deployed_usd
        > user.allocations[s1.strategy_id].capital_deployed_usd
    )


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
