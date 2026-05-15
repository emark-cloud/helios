"""End-to-end loop tick using a stub allocator + stub Goldsky + dry-run runner.

Mirrors the structure of `services/sentinel/tests/test_loop.py` but
exercises the SDK's `AllocatorLoop` directly with a minimal
`BaseAllocator` subclass. The full sentinel-replay parity coverage lands
in PR 2/3 alongside the cutover.
"""

from __future__ import annotations

import pytest
from helios_allocator import BaseAllocator
from helios_allocator.runtime.goldsky import AllocatorGoldsky, StrategyDirectoryRow
from helios_allocator.runtime.loop import AllocatorLoop, LoopConfig
from helios_allocator.runtime.onchain import AllocatorOnChain
from helios_allocator.runtime.state import AllocationState, AllocatorStore, now_ts
from helios_allocator.types import (
    AllocationTarget,
    MetaStrategy,
    StrategyCandidate,
)


class _StubGoldsky(AllocatorGoldsky):
    def __init__(self, rows: list[StrategyDirectoryRow]) -> None:
        self._rows = rows

    async def fetch_directory(self) -> list[StrategyDirectoryRow]:  # type: ignore[override]
        return list(self._rows)

    async def aclose(self) -> None:  # pragma: no cover
        return None


class _AlwaysFirstAllocator(BaseAllocator):
    """Allocates the entire delegation to the first candidate, evenly capped."""

    name = "Stub"
    fee_rate_bps = 0
    supported_classes = ("momentum_v1",)

    def rank_strategies(
        self, user: MetaStrategy, candidates: list[StrategyCandidate]
    ) -> list[float]:
        return [1.0 if i == 0 else 0.0 for i in range(len(candidates))]

    def allocate(
        self,
        user: MetaStrategy,
        ranked: list[StrategyCandidate],
        capital: int,
    ) -> list[AllocationTarget]:
        if not ranked or capital <= 0:
            return []
        c = ranked[0]
        return [
            AllocationTarget(
                strategy_id=c.strategy_id,
                chain_id=c.chain_id,
                capital_usd=capital,
                weight_bps=10_000,
            )
        ]


def _meta() -> MetaStrategy:
    return MetaStrategy(
        user_address="0x" + "ab" * 20,
        allowed_strategy_classes=("momentum_v1",),
        allowed_assets=("USDC",),
        allowed_chains=(2368,),
        max_capital_usd=10_000,
        max_per_strategy_bps=10_000,
        max_strategies_count=2,
        drawdown_threshold_bps=1_500,
        max_fee_rate_bps=2_500,
        rebalance_cadence_sec=900,
        valid_until=2_000_000_000,
    )


def _row(sid: str, *, nav_ts: int | None = None) -> StrategyDirectoryRow:
    return StrategyDirectoryRow(
        strategy_id=sid,
        declared_class="momentum_v1",
        chain_id=2368,
        operator="0x" + "cc" * 20,
        fee_rate_bps=500,
        stake_amount_usd=10_000,
        max_capacity_usd=100_000,
        current_allocations_usd=0,
        reputation_score_e4=8_000,
        trades_attested=120,
        # Default to "fresh" so existing tests pass through the
        # live-NAV filter without each one needing to set the field.
        last_nav_update_ts=nav_ts if nav_ts is not None else now_ts(),
    )


@pytest.mark.asyncio
async def test_first_tick_allocates_idle_capital() -> None:
    store = AllocatorStore()
    user = store.upsert_user(_meta())
    user.delegated_capital_usd = 10_000

    onchain = AllocatorOnChain(
        rpc_url="",
        operator_pk="",
        allocator_vault_address="",
        allocator_registry_address="",
        chain_id=2368,
    )
    goldsky = _StubGoldsky([_row("0x" + "11" * 20)])

    loop = AllocatorLoop(
        store=store,
        allocator=_AlwaysFirstAllocator(),
        goldsky=goldsky,
        onchain=onchain,
        config=LoopConfig(),
    )

    await loop.tick_once(now=now_ts())

    # Dry-run runner records the allocate call; loop emits ALLOCATION_CREATED
    # + REBALANCE_COMPLETE events.
    methods = [c.method for c in onchain.pending]
    assert methods == ["allocateToStrategy"]
    kinds = [e.kind for e in store.recent_events(user.meta.user_address)]
    assert kinds == ["ALLOCATION_CREATED", "REBALANCE_COMPLETE"]


@pytest.mark.asyncio
async def test_swap_cycle_defunds_before_allocates() -> None:
    """When the new target adds a fresh strategy *and* removes an existing
    one (saturating `max_strategies_count`), defund must be submitted first
    or AllocatorVault.allocateToStrategy reverts MetaMaxStrategiesExceeded.
    Reproduces the bug observed against Kite testnet on 2026-05-10.
    """
    store = AllocatorStore()
    user = store.upsert_user(_meta())  # max_strategies_count=2
    user.delegated_capital_usd = 10_000
    user.last_rebalance_ts = now_ts() - 10_000  # past cadence so we rebalance

    sid_old = "0x" + "11" * 20
    sid_new = "0x" + "22" * 20
    # Pre-seed two healthy allocations — exactly at the cap.
    for sid in (sid_old, "0x" + "33" * 20):
        user.allocations[sid] = AllocationState(
            strategy_id=sid,
            chain_id=2368,
            declared_class="momentum_v1",
            capital_deployed_usd=5_000,
            high_water_mark_usd=5_000,
            nav_usd=5_000,
        )

    onchain = AllocatorOnChain(
        rpc_url="",
        operator_pk="",
        allocator_vault_address="",
        allocator_registry_address="",
        chain_id=2368,
    )
    # The stub allocator picks the first directory row; serve `sid_new`
    # (no existing allocation), forcing the diff to drop both olds and
    # add one new.
    goldsky = _StubGoldsky([_row(sid_new)])
    loop = AllocatorLoop(
        store=store,
        allocator=_AlwaysFirstAllocator(),
        goldsky=goldsky,
        onchain=onchain,
    )

    await loop.tick_once(now=now_ts())

    methods = [c.method for c in onchain.pending]
    # All defunds must come before any allocate.
    first_alloc = next(
        (i for i, m in enumerate(methods) if m == "allocateToStrategy"),
        len(methods),
    )
    last_defund = max(
        (i for i, m in enumerate(methods) if m == "defundStrategy"),
        default=-1,
    )
    assert last_defund < first_alloc, methods


class _TiedAllocator(BaseAllocator):
    """Cold-start shape: every candidate scores identically. Funds only
    the top-ranked one, so which strategy stays funded is decided
    entirely by `_compute_target`'s tie-break."""

    name = "Tied"
    fee_rate_bps = 0
    supported_classes = ("momentum_v1",)

    def rank_strategies(
        self, user: MetaStrategy, candidates: list[StrategyCandidate]
    ) -> list[float]:
        return [1.0] * len(candidates)

    def allocate(
        self, user: MetaStrategy, ranked: list[StrategyCandidate], capital: int
    ) -> list[AllocationTarget]:
        if not ranked or capital <= 0:
            return []
        c = ranked[0]
        return [
            AllocationTarget(
                strategy_id=c.strategy_id,
                chain_id=c.chain_id,
                capital_usd=capital,
                weight_bps=10_000,
            )
        ]


@pytest.mark.asyncio
async def test_cold_start_tie_keeps_incumbent_no_rank_drop() -> None:
    """Cold-start steady state: all strategies tied at baseline score.
    A funded incumbent must NOT be defunded just because the candidate
    order flipped between Goldsky refreshes. Without the incumbency
    tie-break the loop would defund the incumbent (RANK_DROP) and
    re-allocate the challenger every cadence, bleeding principal —
    the live bug observed on 2026-05-15.
    """
    store = AllocatorStore()
    user = store.upsert_user(_meta())
    user.delegated_capital_usd = 10_000
    user.last_rebalance_ts = now_ts() - 10_000  # past cadence

    sid_incumbent = "0x" + "11" * 20
    sid_challenger = "0x" + "22" * 20
    user.allocations[sid_incumbent] = AllocationState(
        strategy_id=sid_incumbent,
        chain_id=2368,
        declared_class="momentum_v1",
        capital_deployed_usd=10_000,
        high_water_mark_usd=10_000,
        nav_usd=10_000,
    )

    onchain = AllocatorOnChain(
        rpc_url="",
        operator_pk="",
        allocator_vault_address="",
        allocator_registry_address="",
        chain_id=2368,
    )
    # Serve the challenger FIRST — a plain stable sort on tied scores
    # would put it at rank 0 and displace the incumbent.
    goldsky = _StubGoldsky([_row(sid_challenger), _row(sid_incumbent)])
    loop = AllocatorLoop(
        store=store,
        allocator=_TiedAllocator(),
        goldsky=goldsky,
        onchain=onchain,
    )

    await loop.tick_once(now=now_ts())

    methods = [c.method for c in onchain.pending]
    assert "defundStrategy" not in methods, methods
    kinds = [e.kind for e in store.recent_events(user.meta.user_address)]
    assert "STRATEGY_DEFUNDED" not in kinds, kinds
    assert not user.allocations[sid_incumbent].defunded


@pytest.mark.asyncio
async def test_sub_floor_ops_are_filtered_as_dust() -> None:
    """An op below `min_local_alloc_usd_wei` must not reach the chain —
    moving dust costs more (swap spread + NAV-clamp rounding) than it
    moves. With the gate at 0 the same op executes, proving the gate
    is the cause."""

    async def _run(floor: int) -> list[str]:
        store = AllocatorStore()
        user = store.upsert_user(_meta())
        user.delegated_capital_usd = 500_000  # ~5e5 wei — dust vs 1e15 floor
        onchain = AllocatorOnChain(
            rpc_url="",
            operator_pk="",
            allocator_vault_address="",
            allocator_registry_address="",
            chain_id=2368,
        )
        loop = AllocatorLoop(
            store=store,
            allocator=_AlwaysFirstAllocator(),
            goldsky=_StubGoldsky([_row("0x" + "11" * 20)]),
            onchain=onchain,
            config=LoopConfig(min_local_alloc_usd_wei=floor),
        )
        await loop.tick_once(now=now_ts())
        return [c.method for c in onchain.pending]

    assert await _run(10**15) == []  # dust skipped
    assert await _run(0) == ["allocateToStrategy"]  # gate off → executes


@pytest.mark.asyncio
async def test_stale_nav_strategies_dropped_from_candidates() -> None:
    """Strategies whose navOracle stopped posting drop out of the
    candidate set. Without this filter, a registry row with
    `active=true` but no live operator still attracts capital,
    which is what happened on Kite testnet to the variant vaults
    that had no strategy service driving them.
    """
    store = AllocatorStore()
    user = store.upsert_user(_meta())
    user.delegated_capital_usd = 10_000

    onchain = AllocatorOnChain(
        rpc_url="",
        operator_pk="",
        allocator_vault_address="",
        allocator_registry_address="",
        chain_id=2368,
    )
    fresh_sid = "0x" + "11" * 20
    stale_sid = "0x" + "22" * 20
    never_sid = "0x" + "33" * 20  # never NAV-reported

    now = now_ts()
    goldsky = _StubGoldsky(
        [
            _row(fresh_sid, nav_ts=now - 60),  # 1 min ago → fresh
            _row(stale_sid, nav_ts=now - 24 * 3600),  # 24 hr ago → stale
            _row(never_sid, nav_ts=0),  # never NAV-reported
        ]
    )
    loop = AllocatorLoop(
        store=store,
        allocator=_AlwaysFirstAllocator(),
        goldsky=goldsky,
        onchain=onchain,
        config=LoopConfig(nav_freshness_sec=3600),
    )

    await loop.tick_once(now=now)

    seen = [c.strategy_id for c in loop.candidates]
    assert fresh_sid in seen
    assert stale_sid not in seen
    assert never_sid not in seen


@pytest.mark.asyncio
async def test_nav_filter_disabled_passes_all() -> None:
    """`nav_freshness_sec == 0` disables the filter (back-compat for
    scenario mode + backtests that have no NAV stream)."""
    store = AllocatorStore()
    user = store.upsert_user(_meta())
    user.delegated_capital_usd = 10_000

    onchain = AllocatorOnChain(
        rpc_url="",
        operator_pk="",
        allocator_vault_address="",
        allocator_registry_address="",
        chain_id=2368,
    )
    sids = ["0x" + (h * 2) * 20 for h in "abcd"]
    goldsky = _StubGoldsky([_row(s, nav_ts=0) for s in sids])
    loop = AllocatorLoop(
        store=store,
        allocator=_AlwaysFirstAllocator(),
        goldsky=goldsky,
        onchain=onchain,
        config=LoopConfig(nav_freshness_sec=0),
    )
    await loop.tick_once(now=now_ts())
    assert {c.strategy_id for c in loop.candidates} == set(sids)


@pytest.mark.asyncio
async def test_drawdown_breach_defunds_before_rebalance() -> None:
    store = AllocatorStore()
    user = store.upsert_user(_meta())
    user.delegated_capital_usd = 10_000

    # Pre-seed an allocation already at a 20% drawdown — above the user's
    # 15% threshold, so the first tick must defund before doing anything else.
    sid = "0x" + "11" * 20
    user.allocations[sid] = AllocationState(
        strategy_id=sid,
        chain_id=2368,
        declared_class="momentum_v1",
        capital_deployed_usd=5_000,
        high_water_mark_usd=5_000,
        nav_usd=4_000,  # 20% drawdown
    )

    onchain = AllocatorOnChain(
        rpc_url="",
        operator_pk="",
        allocator_vault_address="",
        allocator_registry_address="",
        chain_id=2368,
    )
    goldsky = _StubGoldsky([_row(sid)])
    loop = AllocatorLoop(
        store=store,
        allocator=_AlwaysFirstAllocator(),
        goldsky=goldsky,
        onchain=onchain,
    )

    await loop.tick_once(now=now_ts())

    methods = [c.method for c in onchain.pending]
    # First call must be the defund. (Subsequent allocate is fine — the
    # allocator chose the same strategy from the directory.)
    assert methods[0] == "defundStrategy"
    assert methods[0:1] == ["defundStrategy"]
    kinds = [e.kind for e in store.recent_events(user.meta.user_address)]
    assert "STRATEGY_DEFUNDED" in kinds


def _row_chain(sid: str, chain_id: int, *, nav_ts: int | None = None) -> StrategyDirectoryRow:
    return StrategyDirectoryRow(
        strategy_id=sid,
        declared_class="momentum_v1",
        chain_id=chain_id,
        operator="0x" + "cc" * 20,
        fee_rate_bps=500,
        stake_amount_usd=10_000,
        max_capacity_usd=100_000,
        current_allocations_usd=0,
        reputation_score_e4=8_000,
        trades_attested=120,
        last_nav_update_ts=nav_ts if nav_ts is not None else now_ts(),
    )


@pytest.mark.asyncio
async def test_remote_chain_allocation_defers_and_skips_onchain_submit() -> None:
    """Phase-1 chain-aware allocation invariant: a target whose
    `chain_id` does not match the on-chain runner's chain MUST NOT
    reach `AllocatorVault.allocateToStrategy`. Instead the loop emits
    `CROSS_CHAIN_ALLOCATION_DEFERRED` for the operator / dashboard.

    Background: Sentinel's CXR-4 candidate fan-out now sees Base + Arb
    strategies, but the on-chain `AllocatorVault` only has them
    registered on their *local* StrategyRegistry — submitting to the
    Kite vault reverts `StrategyNotRegistered`. The fix lives in
    `AllocatorLoop._defer_remote_ops`; this test pins the contract so
    a future refactor can't silently re-introduce the cross-chain
    revert.
    """
    store = AllocatorStore()
    user = store.upsert_user(_meta())
    user.delegated_capital_usd = 10_000

    onchain = AllocatorOnChain(
        rpc_url="",
        operator_pk="",
        allocator_vault_address="",
        allocator_registry_address="",
        chain_id=2368,  # local = Kite testnet
    )
    base_sid = "0x" + "bb" * 20
    goldsky = _StubGoldsky([_row_chain(base_sid, 84_532)])  # Base-Sepolia
    loop = AllocatorLoop(
        store=store,
        allocator=_AlwaysFirstAllocator(),
        goldsky=goldsky,
        onchain=onchain,
    )

    await loop.tick_once(now=now_ts())

    # Critical: zero on-chain calls. The Kite AllocatorVault never sees
    # the Base strategyId, so the call shape can't even attempt to
    # revert.
    assert onchain.pending == []

    # The deferred allocation is visible to the dashboard as a distinct
    # event kind, and `user.allocations` is not mutated (no fake
    # capital_deployed mirror — until real capital bridges, it isn't
    # deployed).
    events = store.recent_events(user.meta.user_address)
    deferred = [e for e in events if e.kind == "CROSS_CHAIN_ALLOCATION_DEFERRED"]
    assert len(deferred) == 1
    assert deferred[0].strategy_id == base_sid
    assert deferred[0].amount_usd > 0
    assert "84532" in deferred[0].reason  # chain id surfaced in reason
    assert base_sid not in user.allocations


@pytest.mark.asyncio
async def test_remote_chain_with_cxr_wired_submits_live_allocate_to_remote() -> None:
    """CXR-0c — when the OFT bridge is wired (OFT adapter + EID map),
    the loop flips a remote target from defer-mode to a real
    `allocateToRemoteStrategy` call. The OnChainCall captures
    method=allocateToRemoteStrategy, the dstEid, and the strategy id
    encoded as bytes32 of the vault address. The event emitted is
    `CROSS_CHAIN_ALLOCATION_SUBMITTED`, not `DEFERRED`.
    """
    store = AllocatorStore()
    user = store.upsert_user(_meta())
    user.delegated_capital_usd = 10_000

    onchain = AllocatorOnChain(
        rpc_url="",
        operator_pk="",
        allocator_vault_address="",
        allocator_registry_address="",
        chain_id=2368,
        oft_adapter_address="0x" + "ee" * 20,
        remote_chain_eids={84_532: 40_245, 421_614: 40_231},
    )
    base_sid = "0x" + "bb" * 20
    goldsky = _StubGoldsky([_row_chain(base_sid, 84_532)])
    loop = AllocatorLoop(
        store=store,
        allocator=_AlwaysFirstAllocator(),
        goldsky=goldsky,
        onchain=onchain,
        # CXR cost Tier 1 defaults gate sub-$10 deltas (10e18 wei) — the
        # stub's 10_000-wei delta would silently skip. Disable both
        # gates so this test exercises the original CXR-0c contract
        # shape, not the Tier 1 cost suppression. The threshold gate
        # has dedicated coverage below.
        config=LoopConfig(
            min_cross_chain_alloc_usd_wei=0,
            cross_chain_flush_cadence_sec=0,
        ),
    )

    await loop.tick_once(now=now_ts())

    # The one pending call is the cross-chain submission, not the
    # local allocateToStrategy.
    assert len(onchain.pending) == 1
    call = onchain.pending[0]
    assert call.method == "allocateToRemoteStrategy"
    assert call.dst_eid == 40_245  # Base EID
    assert call.remote_vault.lower() == base_sid.lower()
    # strategyId is the bytes32 left-padding of the vault address.
    assert call.strategy_id_bytes32.endswith(bytes.fromhex(base_sid[2:]))

    events = store.recent_events(user.meta.user_address)
    submitted = [e for e in events if e.kind == "CROSS_CHAIN_ALLOCATION_SUBMITTED"]
    assert len(submitted) == 1
    assert submitted[0].strategy_id == base_sid
    # Defer event should NOT also be emitted.
    deferred = [e for e in events if e.kind == "CROSS_CHAIN_ALLOCATION_DEFERRED"]
    assert deferred == []


@pytest.mark.asyncio
async def test_remote_chain_deferral_doesnt_block_local_allocation() -> None:
    """When a tick produces a mixed local + remote target list, the
    local side still allocates normally and the remote side defers.
    The mixed-state invariant matters because pre-fix Sentinel would
    either short-circuit the whole rebalance (skip local too) or
    submit remote and revert — neither is correct."""

    class _SplitAllocator(BaseAllocator):
        name = "Split"
        fee_rate_bps = 0
        supported_classes = ("momentum_v1",)

        def rank_strategies(
            self, user: MetaStrategy, candidates: list[StrategyCandidate]
        ) -> list[float]:
            return [1.0 for _ in candidates]

        def allocate(
            self,
            user: MetaStrategy,
            ranked: list[StrategyCandidate],
            capital: int,
        ) -> list[AllocationTarget]:
            half = capital // 2
            return [
                AllocationTarget(
                    strategy_id=c.strategy_id,
                    chain_id=c.chain_id,
                    capital_usd=half,
                    weight_bps=5_000,
                )
                for c in ranked[:2]
            ]

    store = AllocatorStore()
    user = store.upsert_user(_meta())
    user.delegated_capital_usd = 10_000

    onchain = AllocatorOnChain(
        rpc_url="",
        operator_pk="",
        allocator_vault_address="",
        allocator_registry_address="",
        chain_id=2368,
    )
    local_sid = "0x" + "11" * 20
    remote_sid = "0x" + "22" * 20
    goldsky = _StubGoldsky(
        [
            _row_chain(local_sid, 2368),
            _row_chain(remote_sid, 84_532),
        ]
    )
    loop = AllocatorLoop(
        store=store,
        allocator=_SplitAllocator(),
        goldsky=goldsky,
        onchain=onchain,
    )

    await loop.tick_once(now=now_ts())

    submitted = [c.strategy for c in onchain.pending if c.method == "allocateToStrategy"]
    assert submitted == [local_sid]

    deferred = [
        e
        for e in store.recent_events(user.meta.user_address)
        if e.kind == "CROSS_CHAIN_ALLOCATION_DEFERRED"
    ]
    assert [d.strategy_id for d in deferred] == [remote_sid]


@pytest.mark.asyncio
async def test_zero_chain_id_target_is_treated_as_local() -> None:
    """A target with `chain_id == 0` (legacy un-tagged Goldsky row,
    test fixture without an explicit chain) must NOT trigger the
    cross-chain deferral path — otherwise every pre-CXR-4 scenario
    suddenly behaves differently. Local-or-zero is the local case."""
    store = AllocatorStore()
    user = store.upsert_user(_meta())
    user.delegated_capital_usd = 10_000

    onchain = AllocatorOnChain(
        rpc_url="",
        operator_pk="",
        allocator_vault_address="",
        allocator_registry_address="",
        chain_id=2368,
    )
    legacy_sid = "0x" + "33" * 20
    # `chain_id=0` mimics legacy directory rows.
    goldsky = _StubGoldsky([_row_chain(legacy_sid, 0)])
    loop = AllocatorLoop(
        store=store,
        allocator=_AlwaysFirstAllocator(),
        goldsky=goldsky,
        onchain=onchain,
    )

    await loop.tick_once(now=now_ts())

    methods = [c.method for c in onchain.pending]
    assert methods == ["allocateToStrategy"]
    kinds = [e.kind for e in store.recent_events(user.meta.user_address)]
    assert "CROSS_CHAIN_ALLOCATION_DEFERRED" not in kinds


@pytest.mark.asyncio
async def test_unallocated_strategy_never_emits_defund() -> None:
    """Regression for the legacy-vault defund symptom: after a registry
    redeploy, the prior cohort of strategy vaults is still on-chain but
    the user was never allocated to them. The loop's diff must not emit
    defunds for sids absent from `user.allocations` — those calls would
    revert `StrategyNotAllocated()` on AllocatorVault and pollute the
    activity log. Captures the invariant added to `_diff_allocations`.
    """
    store = AllocatorStore()
    user = store.upsert_user(_meta())
    user.delegated_capital_usd = 10_000

    sid_active = "0x" + "11" * 20  # current target
    sid_ghost = "0x" + "ee" * 20  # legacy vault — never allocated

    onchain = AllocatorOnChain(
        rpc_url="",
        operator_pk="",
        allocator_vault_address="",
        allocator_registry_address="",
        chain_id=2368,
    )
    # Directory only knows about the active vault — the ghost is absent
    # (it was filtered upstream by `active=true` or the live-NAV gate).
    goldsky = _StubGoldsky([_row(sid_active)])
    loop = AllocatorLoop(
        store=store,
        allocator=_AlwaysFirstAllocator(),
        goldsky=goldsky,
        onchain=onchain,
    )

    await loop.tick_once(now=now_ts())

    defunds = [c for c in onchain.pending if c.method == "defundStrategy"]
    # The ghost must not appear in any defund call — neither as the target
    # nor anywhere else in the pending op list.
    assert all(c.strategy != sid_ghost for c in onchain.pending)
    assert defunds == []  # first tick allocates; no prior state to drain


# ── CXR cost Tier 1 — threshold + flush cadence gates ────────────────


def _cxr_wired_onchain() -> AllocatorOnChain:
    return AllocatorOnChain(
        rpc_url="",
        operator_pk="",
        allocator_vault_address="",
        allocator_registry_address="",
        chain_id=2368,
        oft_adapter_address="0x" + "ee" * 20,
        remote_chain_eids={84_532: 40_245, 421_614: 40_231},
    )


@pytest.mark.asyncio
async def test_cross_chain_below_threshold_skipped_silently() -> None:
    """Tier 1 — a cross-chain delta below `min_cross_chain_alloc_usd_wei`
    must not fire `allocateToRemoteStrategy` (~1 KITE LZ V2 floor) and
    must not emit a deferred event. The op is silently queued so a
    later tick with an accumulated delta crosses the threshold.

    Stub flow: delegated_capital_usd=10_000 (delta=10_000 since the
    user has no prior allocations); threshold set higher than the
    delta. Expect zero on-chain calls AND zero submitted/deferred
    events for the cross-chain strategy.
    """
    store = AllocatorStore()
    user = store.upsert_user(_meta())
    user.delegated_capital_usd = 10_000

    onchain = _cxr_wired_onchain()
    remote_sid = "0x" + "bb" * 20
    goldsky = _StubGoldsky([_row_chain(remote_sid, 84_532)])
    loop = AllocatorLoop(
        store=store,
        allocator=_AlwaysFirstAllocator(),
        goldsky=goldsky,
        onchain=onchain,
        config=LoopConfig(
            # Threshold an order of magnitude above the stub delta so
            # the gate definitely catches.
            min_cross_chain_alloc_usd_wei=100_000,
            cross_chain_flush_cadence_sec=0,
        ),
    )

    await loop.tick_once(now=now_ts())

    # Critical: the LZ V2 fixed-fee submit must NOT fire.
    assert all(c.method != "allocateToRemoteStrategy" for c in onchain.pending)
    events = store.recent_events(user.meta.user_address)
    submitted = [e for e in events if e.kind == "CROSS_CHAIN_ALLOCATION_SUBMITTED"]
    deferred = [e for e in events if e.kind == "CROSS_CHAIN_ALLOCATION_DEFERRED"]
    # No event at all — threshold-skipped ops are silent (log-only) since
    # the next tick reassesses the cumulative delta.
    assert submitted == []
    assert deferred == []


@pytest.mark.asyncio
async def test_cross_chain_above_threshold_submits_normally() -> None:
    """Tier 1 — a cross-chain delta above the threshold fires the
    submit normally. Sanity-check that the gate doesn't swallow
    legitimate deltas.
    """
    store = AllocatorStore()
    user = store.upsert_user(_meta())
    user.delegated_capital_usd = 10_000

    onchain = _cxr_wired_onchain()
    remote_sid = "0x" + "bb" * 20
    goldsky = _StubGoldsky([_row_chain(remote_sid, 84_532)])
    loop = AllocatorLoop(
        store=store,
        allocator=_AlwaysFirstAllocator(),
        goldsky=goldsky,
        onchain=onchain,
        config=LoopConfig(
            # Threshold well below the stub 10_000 delta so the gate is
            # a no-op.
            min_cross_chain_alloc_usd_wei=100,
            cross_chain_flush_cadence_sec=0,
        ),
    )

    await loop.tick_once(now=now_ts())

    remote_calls = [c for c in onchain.pending if c.method == "allocateToRemoteStrategy"]
    assert len(remote_calls) == 1
    events = store.recent_events(user.meta.user_address)
    submitted = [e for e in events if e.kind == "CROSS_CHAIN_ALLOCATION_SUBMITTED"]
    assert len(submitted) == 1


@pytest.mark.asyncio
async def test_cross_chain_flush_cadence_suppresses_repeat_fires() -> None:
    """Tier 1 — once a cross-chain submit lands, subsequent ticks
    within `cross_chain_flush_cadence_sec` MUST NOT fire a second LZ
    V2 send for the same (user, strategyId). The deferred path doesn't
    mutate `user.allocations` (capital is only credited when the
    destination chain confirms), so without this gate every 60s tick
    would re-fire and burn another ~1 KITE.

    Three-tick scenario:
      t=0     → fires once (first cross-chain submit)
      t=120   → within 300s window → suppressed (no new call, no new event)
      t=400   → outside 300s window → fires again

    The meta-strategy uses `rebalance_cadence_sec=60` so the user-level
    rebalance gate doesn't dominate the per-(user, strategyId) flush
    gate we're actually testing.
    """
    store = AllocatorStore()
    meta = _meta()
    # Lower the user-level cadence so ticks 2 + 3 actually reach
    # `_apply_diffs` → `_defer_remote_ops`. Default 900s would gate
    # both before they hit the flush window we're testing.
    short_cadence_meta = MetaStrategy(**{**meta.__dict__, "rebalance_cadence_sec": 60})
    user = store.upsert_user(short_cadence_meta)
    user.delegated_capital_usd = 10_000

    onchain = _cxr_wired_onchain()
    remote_sid = "0x" + "bb" * 20
    goldsky = _StubGoldsky([_row_chain(remote_sid, 84_532)])
    loop = AllocatorLoop(
        store=store,
        allocator=_AlwaysFirstAllocator(),
        goldsky=goldsky,
        onchain=onchain,
        config=LoopConfig(
            min_cross_chain_alloc_usd_wei=0,  # disable threshold gate
            cross_chain_flush_cadence_sec=300,
        ),
    )

    t0 = now_ts()
    await loop.tick_once(now=t0)
    after_first = len([c for c in onchain.pending if c.method == "allocateToRemoteStrategy"])
    assert after_first == 1

    # Tick inside the flush window — must not fire a second send.
    # t0 + 120 is past the user-level 60s cadence gate but well inside
    # the 300s flush window.
    await loop.tick_once(now=t0 + 120)
    after_window = len([c for c in onchain.pending if c.method == "allocateToRemoteStrategy"])
    assert after_window == 1, "in-window tick should be suppressed"

    # Tick outside the flush window — fires again. The deferred path
    # never mutates `user.allocations`, so the diff still produces a
    # positive delta and the now-eligible op resubmits.
    await loop.tick_once(now=t0 + 400)
    after_flush = len([c for c in onchain.pending if c.method == "allocateToRemoteStrategy"])
    assert after_flush == 2, "post-window tick should resubmit"


class _MultiCandidateAllocator(BaseAllocator):
    """Spreads capital evenly across all candidates. Used to drive
    multi-strategy targets in Tier 2 batching tests."""

    name = "MultiSpread"
    fee_rate_bps = 0
    supported_classes = ("momentum_v1",)

    def rank_strategies(
        self, user: MetaStrategy, candidates: list[StrategyCandidate]
    ) -> list[float]:
        return [1.0 for _ in candidates]

    def allocate(
        self,
        user: MetaStrategy,
        ranked: list[StrategyCandidate],
        capital: int,
    ) -> list[AllocationTarget]:
        if not ranked or capital <= 0:
            return []
        share = capital // len(ranked)
        return [
            AllocationTarget(
                strategy_id=c.strategy_id,
                chain_id=c.chain_id,
                capital_usd=share,
                weight_bps=10_000 // len(ranked),
            )
            for c in ranked
        ]


@pytest.mark.asyncio
async def test_cross_chain_two_strategies_same_chain_collapse_to_one_batch_send() -> None:
    """Tier 2 — the headline cost lever. Two cross-chain targets on
    the same destination chain (mom.base + mr.base) MUST submit one
    `allocateToRemoteStrategyBatch` instead of two
    `allocateToRemoteStrategy` calls. That's where the ~33% LZ V2 fee
    saving on a multi-candidate rebalance comes from.

    Pins the invariant by counting on-chain call shapes — the loop
    groups remote ops by dst_eid and flushes via batch when N>1.
    """
    store = AllocatorStore()
    meta = _meta()
    # Need max_strategies_count >= 2 so the second candidate isn't
    # pruned by the meta-strategy gate.
    multi_meta = MetaStrategy(**{**meta.__dict__, "max_strategies_count": 4})
    user = store.upsert_user(multi_meta)
    # Use 18-dec canonical scale so per-entry amounts survive the
    # OFT shared-decimals floor (10^12). $100 split two ways → 50e18
    # per entry, comfortably above the floor.
    user.delegated_capital_usd = 100 * 10**18

    onchain = _cxr_wired_onchain()
    sid_a = "0x" + "aa" * 20
    sid_b = "0x" + "bb" * 20
    goldsky = _StubGoldsky(
        [_row_chain(sid_a, 84_532), _row_chain(sid_b, 84_532)]  # both on Base
    )
    loop = AllocatorLoop(
        store=store,
        allocator=_MultiCandidateAllocator(),
        goldsky=goldsky,
        onchain=onchain,
        config=LoopConfig(
            min_cross_chain_alloc_usd_wei=0,
            cross_chain_flush_cadence_sec=0,
        ),
    )

    await loop.tick_once(now=now_ts())

    # Exactly ONE batched call, not two single-call sends. Confirms
    # the LZ V2 fee was paid once for both strategies.
    batch_calls = [c for c in onchain.pending if c.method == "allocateToRemoteStrategyBatch"]
    single_calls = [c for c in onchain.pending if c.method == "allocateToRemoteStrategy"]
    assert len(batch_calls) == 1, "should batch same-chain ops into one send"
    assert len(single_calls) == 0, "no single-call send when N>1 on same chain"
    # Both strategies appear in the batched call's payload.
    batch = batch_calls[0]
    assert set(batch.batch_strategy_ids) == {sid_a, sid_b}
    assert batch.dst_eid == 40_245  # Base EID
    assert len(batch.batch_amounts) == 2

    # Per-strategy SUBMITTED events still fire — UI dashboard sees one
    # event per strategy, both sharing the batch's tx hash.
    events = store.recent_events(user.meta.user_address)
    submitted = [e for e in events if e.kind == "CROSS_CHAIN_ALLOCATION_SUBMITTED"]
    assert len(submitted) == 2, "one event per strategy in the batch"


@pytest.mark.asyncio
async def test_cross_chain_two_strategies_different_chains_fire_two_single_sends() -> None:
    """Tier 2 invariant — only ops on the SAME destination chain can
    batch. A mom.base + yr.arb pair must fire two separate sends, one
    per chain. Pins that the grouping key is dst_chain_id, not "any
    cross-chain op".
    """
    store = AllocatorStore()
    meta = _meta()
    multi_meta = MetaStrategy(**{**meta.__dict__, "max_strategies_count": 4})
    user = store.upsert_user(multi_meta)
    # Use 18-dec canonical scale so per-entry amounts survive the
    # OFT shared-decimals floor (10^12). $100 split two ways → 50e18
    # per entry, comfortably above the floor.
    user.delegated_capital_usd = 100 * 10**18

    onchain = _cxr_wired_onchain()
    sid_base = "0x" + "bb" * 20
    sid_arb = "0x" + "aa" * 20
    goldsky = _StubGoldsky([_row_chain(sid_base, 84_532), _row_chain(sid_arb, 421_614)])
    loop = AllocatorLoop(
        store=store,
        allocator=_MultiCandidateAllocator(),
        goldsky=goldsky,
        onchain=onchain,
        config=LoopConfig(
            min_cross_chain_alloc_usd_wei=0,
            cross_chain_flush_cadence_sec=0,
        ),
    )

    await loop.tick_once(now=now_ts())

    # Two single-call sends (one per chain), zero batch calls.
    batch_calls = [c for c in onchain.pending if c.method == "allocateToRemoteStrategyBatch"]
    single_calls = [c for c in onchain.pending if c.method == "allocateToRemoteStrategy"]
    assert len(batch_calls) == 0, "different-chain ops can't share a batch"
    assert len(single_calls) == 2
    assert {c.dst_eid for c in single_calls} == {40_245, 40_231}


@pytest.mark.asyncio
async def test_cross_chain_threshold_zero_disables_gate() -> None:
    """Tier 1 — setting threshold to 0 fully disables the gate for
    back-compat with tests and dry-runs that allocate dust amounts.
    Pinning the disable knob protects scenario-mode replays + the
    existing `test_remote_chain_with_cxr_wired_submits_live_allocate_to_remote`
    contract from a future regression where the threshold default
    creeps up and accidentally silences live-bridge tests.
    """
    store = AllocatorStore()
    user = store.upsert_user(_meta())
    user.delegated_capital_usd = 1  # dust delta

    onchain = _cxr_wired_onchain()
    remote_sid = "0x" + "bb" * 20
    goldsky = _StubGoldsky([_row_chain(remote_sid, 84_532)])
    loop = AllocatorLoop(
        store=store,
        allocator=_AlwaysFirstAllocator(),
        goldsky=goldsky,
        onchain=onchain,
        config=LoopConfig(
            min_cross_chain_alloc_usd_wei=0,
            cross_chain_flush_cadence_sec=0,
        ),
    )

    await loop.tick_once(now=now_ts())
    # The stub `allocate_to_remote` records the call even when amount
    # floors to 0 (`_CONVERSION = 10^12` strips dust). What we're
    # pinning is that the threshold=0 setting did NOT trip the gate
    # before the dust floor.
    remote_calls = [c for c in onchain.pending if c.method == "allocateToRemoteStrategy"]
    assert len(remote_calls) == 1
