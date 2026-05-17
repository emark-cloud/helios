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
from helios_allocator.runtime.onchain import AllocatorOnChain, OnChainCall
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


# Default permits the CXR destination chains: the cross-chain tests
# feed Base/Arb candidates and exercise the defer/bridge mechanics,
# which only make sense when the destination is within the user's
# signed mandate. Kite-only tests feed 2368/0 candidates, for which
# the `allowed_chains` gate is a no-op, so the wider default doesn't
# change their behaviour. `test_off_policy_chain_is_gated_out`
# overrides with Kite-only to pin the gate itself.
def _meta(allowed_chains: tuple[int, ...] = (2368, 84_532, 421_614)) -> MetaStrategy:
    return MetaStrategy(
        user_address="0x" + "ab" * 20,
        allowed_strategy_classes=("momentum_v1",),
        allowed_assets=("USDC",),
        allowed_chains=allowed_chains,
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


def test_watched_strategy_ids_reflects_active_directory() -> None:
    """`watched_strategy_ids` is a sync snapshot of the Goldsky `active`
    directory (`_directory`), not the NAV-filtered candidate set — a
    temporarily NAV-silent but active vault must still be watched. This
    is what `chain_watch` reads to auto-track new strategies."""
    store = AllocatorStore()
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
        goldsky=_StubGoldsky([]),
        onchain=onchain,
    )
    assert loop.watched_strategy_ids == ()  # nothing before first refresh
    a, b = "0x" + "11" * 20, "0x" + "22" * 20
    loop.seed_directory([_row(a), _row(b)])
    assert loop.watched_strategy_ids == (a, b)


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
            # v1 ships cross-chain capital OFF by default; these tests
            # exercise the live OFT.send path so opt in explicitly.
            cross_chain_capital_enabled=True,
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
            # Live-path test: opt in past the v1 capital kill-switch so
            # the op reaches the Tier-1 threshold gate under test.
            cross_chain_capital_enabled=True,
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
            # Live-path test: opt in past the v1 capital kill-switch.
            cross_chain_capital_enabled=True,
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
            # Live-path test: opt in past the v1 capital kill-switch.
            cross_chain_capital_enabled=True,
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
    # Works in 18-dec canonical wei (delegated = 100e18) so per-entry
    # amounts clear the OFT shared-decimals floor (1e12). `_compute_target`
    # lifts `max_capital_usd` into wei (`* _USD_WEI_SCALE`), so the toy
    # `_meta()` cap of 10_000 USD = 1e22 wei comfortably exceeds the
    # 100e18 delegated and the clamp is a no-op here.
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
            # v1 ships cross-chain capital OFF by default; these tests
            # exercise the live OFT.send path so opt in explicitly.
            cross_chain_capital_enabled=True,
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
    # Works in 18-dec canonical wei (delegated = 100e18) so per-entry
    # amounts clear the OFT shared-decimals floor (1e12). `_compute_target`
    # lifts `max_capital_usd` into wei (`* _USD_WEI_SCALE`), so the toy
    # `_meta()` cap of 10_000 USD = 1e22 wei comfortably exceeds the
    # 100e18 delegated and the clamp is a no-op here.
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
            # v1 ships cross-chain capital OFF by default; these tests
            # exercise the live OFT.send path so opt in explicitly.
            cross_chain_capital_enabled=True,
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
            # v1 ships cross-chain capital OFF by default; these tests
            # exercise the live OFT.send path so opt in explicitly.
            cross_chain_capital_enabled=True,
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


# ── Regression: cap-aware sizing + reconciled store + chain policy ──


class _DeployedOnChain(AllocatorOnChain):
    """Stub that reports a non-zero on-chain `userTotalDeployed` (an
    orphan from a prior onboard the in-memory store doesn't track) and
    leaves the seeded delegated balance in place."""

    def __init__(self, deployed: int) -> None:
        super().__init__(
            rpc_url="",
            operator_pk="",
            allocator_vault_address="",
            allocator_registry_address="",
            chain_id=2368,
        )
        self._deployed = deployed

    async def read_user_total_deployed_async(self, user: str) -> int | None:
        return self._deployed

    async def read_user_vault_balance_async(self, user: str) -> int | None:
        return None  # keep the test-seeded delegated balance


class _RejectingOnChain(AllocatorOnChain):
    """Stub whose `allocateToStrategy` reverts on-chain (the
    MetaCapacityExceeded shape from the re-onboard incident)."""

    def __init__(self) -> None:
        super().__init__(
            rpc_url="",
            operator_pk="",
            allocator_vault_address="",
            allocator_registry_address="",
            chain_id=2368,
        )

    async def allocate_async(self, user: str, strategy: str, amount: int) -> OnChainCall:
        return OnChainCall(
            method="allocateToStrategy",
            user=user,
            strategy=strategy,
            amount=amount,
            error="('0xccdb4f34', '0xccdb4f34')",  # MetaCapacityExceeded
        )

    async def read_user_vault_balance_async(self, user: str) -> int | None:
        return None


@pytest.mark.asyncio
async def test_target_clamps_to_meta_cap_minus_orphaned_deployed() -> None:
    """Fix #1 + #3 — the loop must size within the on-chain meta-capital
    headroom, not off the raw UserVault balance, and must subtract the
    orphaned on-chain principal (deployed under a prior onboard, not in
    this store) so `userTotalDeployed + new <= maxCapital` holds.

    All capital quantities are 18-dec canonical wei (UserVault balance
    + `userTotalDeployed` are raw wei; `_compute_target` lifts the
    human `max_capital_usd` into wei via `_USD_WEI_SCALE`). Pins the
    exact incident: delegated 50_000 >> maxCapital 10_000, 3_000
    already deployed on-chain → deployable budget is
    min(50_000, 10_000) - 3_000 = 7_000 (all × 1e18)."""
    store = AllocatorStore()
    user = store.upsert_user(_meta())  # max_capital_usd=10_000 → 1e22 wei
    user.delegated_capital_usd = 50_000 * 10**18

    sid = "0x" + "11" * 20
    goldsky = _StubGoldsky([_row(sid)])  # Kite, chain 2368
    loop = AllocatorLoop(
        store=store,
        allocator=_AlwaysFirstAllocator(),
        goldsky=goldsky,
        onchain=_DeployedOnChain(deployed=3_000 * 10**18),
    )

    await loop.tick_once(now=now_ts())

    assert sid in user.allocations
    assert user.allocations[sid].capital_deployed_usd == 7_000 * 10**18


@pytest.mark.asyncio
async def test_orphaned_deployed_exhausts_cap_yields_no_target() -> None:
    """Fix #3 — when the orphaned on-chain principal already meets (or
    exceeds) maxCapital there is no headroom; the loop must allocate
    nothing rather than submit a doomed `allocateToStrategy`. All
    quantities are 18-dec canonical wei."""
    store = AllocatorStore()
    user = store.upsert_user(_meta())  # max_capital_usd=10_000 → 1e22 wei
    user.delegated_capital_usd = 50_000 * 10**18

    sid = "0x" + "11" * 20
    goldsky = _StubGoldsky([_row(sid)])
    loop = AllocatorLoop(
        store=store,
        allocator=_AlwaysFirstAllocator(),
        goldsky=goldsky,
        onchain=_DeployedOnChain(deployed=10_000 * 10**18),
    )

    await loop.tick_once(now=now_ts())

    assert sid not in user.allocations


class _LiquidDeployedOnChain(AllocatorOnChain):
    """Stub returning a *real* liquid UserVault balance AND a non-zero
    `userTotalDeployed` — the consistent-read state the live churn bug
    needs. `_DeployedOnChain` returns balance=None (keeps the seeded
    total), so it never exercises `_tick_user`'s liquid+deployed
    reconstitution; this one does."""

    def __init__(self, *, liquid: int, deployed: int) -> None:
        super().__init__(
            rpc_url="",
            operator_pk="",
            allocator_vault_address="",
            allocator_registry_address="",
            chain_id=2368,
        )
        self._liquid = liquid
        self._deployed = deployed

    async def read_user_vault_balance_async(self, user: str) -> int | None:
        return self._liquid

    async def read_user_total_deployed_async(self, user: str) -> int | None:
        return self._deployed


@pytest.mark.asyncio
async def test_fully_allocated_user_consistent_reads_no_mass_defund() -> None:
    """Regression: a fully-allocated user must NOT have every allocation
    torn down the moment the RPC returns a *consistent* non-zero
    `userTotalDeployed`.

    `read_user_vault_balance` is the UserVault's *liquid* balance — it
    shrinks as capital is routed out. Pre-fix, `_tick_user` set
    `delegated_capital_usd = liquid` alone, so `_compute_target`
    budgeted against the liquid remainder (far below the current
    allocation) and the diff defunded everything (mislabelled
    `RANK_DROP`), then re-allocated next cadence — a churn loop that
    bled swap spread + gas and never durably deployed. A flaky Kite RPC
    intermittently reading `deployed=0` had masked it. Pins the live
    incident (user 0x1cFCD4e1…, 2026-05-17): 1837.84 deployed, 162.16
    liquid, all 3 defunded once the read went consistent.

    Fix: `_tick_user` reconstitutes the true total =
    `liquid + userTotalDeployed`. Setup: 9_000 deployed to one
    strategy, 1_000 liquid, `userTotalDeployed == managed` (no orphan).
    Fixed delegated = 1_000 + 9_000 = 10_000; budget = min(10_000, cap
    10_000) − orphan(0) = 10_000 ⇒ the idle 1_000 is *added* to the
    position (correct), nothing defunded. Pre-fix delegated = 1_000 ⇒
    budget 1_000 ⇒ −8_000 decrease ⇒ STRATEGY_DEFUNDED."""
    store = AllocatorStore()
    user = store.upsert_user(_meta())  # max_capital_usd=10_000 → 1e22 wei cap
    sid = "0x" + "11" * 20
    deployed = 9_000 * 10**18
    user.allocations[sid] = AllocationState(
        strategy_id=sid,
        chain_id=2368,
        declared_class="momentum_v1",
        capital_deployed_usd=deployed,
        high_water_mark_usd=deployed,
        nav_usd=deployed,
        last_rebalance_ts=0,
    )
    user.last_rebalance_ts = 0

    goldsky = _StubGoldsky([_row(sid)])
    # Liquid UserVault balance = total delegation − the deployed bulk;
    # userTotalDeployed == the seeded allocation (no untracked orphan).
    onchain = _LiquidDeployedOnChain(liquid=1_000 * 10**18, deployed=deployed)
    loop = AllocatorLoop(
        store=store,
        allocator=_AlwaysFirstAllocator(),
        goldsky=goldsky,
        onchain=onchain,
    )

    await loop.tick_once(now=now_ts())

    # The allocation must survive — not torn down. Pre-fix this defunded.
    assert sid in user.allocations
    assert not user.allocations[sid].defunded
    # delegated reconstituted to the true total (liquid + deployed).
    assert user.delegated_capital_usd == 10_000 * 10**18
    # Idle remainder deployed (grew to the full delegation), not removed.
    assert user.allocations[sid].capital_deployed_usd == 10_000 * 10**18
    kinds = [e.kind for e in store.recent_events(user.meta.user_address)]
    assert "STRATEGY_DEFUNDED" not in kinds
    assert "defundStrategy" not in [c.method for c in onchain.pending]


@pytest.mark.asyncio
async def test_onchain_rejected_allocate_not_mirrored_into_store() -> None:
    """Fix #2 — a reverted `allocateToStrategy` must NOT bump the
    in-memory store. Pre-fix the dashboard showed capital that never
    landed on-chain because the mirror ran unconditionally."""
    store = AllocatorStore()
    user = store.upsert_user(_meta())
    user.delegated_capital_usd = 10_000 * 10**18

    sid = "0x" + "11" * 20
    goldsky = _StubGoldsky([_row(sid)])
    loop = AllocatorLoop(
        store=store,
        allocator=_AlwaysFirstAllocator(),
        goldsky=goldsky,
        onchain=_RejectingOnChain(),
    )

    await loop.tick_once(now=now_ts())

    assert sid not in user.allocations
    events = store.recent_events(user.meta.user_address)
    assert not [e for e in events if e.kind in ("ALLOCATION_CREATED", "ALLOCATION_INCREASED")]


@pytest.mark.asyncio
async def test_off_policy_chain_is_gated_out() -> None:
    """Fix #4 — a candidate on a chain outside the user's signed
    `allowed_chains` must produce no target at all: no local submit, no
    cross-chain defer, no bridge. Contrast
    `test_remote_chain_allocation_defers_and_skips_onchain_submit`,
    where the remote chain IS within the (default) mandate and so
    legitimately defers."""
    store = AllocatorStore()
    user = store.upsert_user(_meta(allowed_chains=(2368,)))  # Kite-only mandate
    user.delegated_capital_usd = 10_000 * 10**18

    onchain = AllocatorOnChain(
        rpc_url="",
        operator_pk="",
        allocator_vault_address="",
        allocator_registry_address="",
        chain_id=2368,
    )
    base_sid = "0x" + "bb" * 20
    goldsky = _StubGoldsky([_row_chain(base_sid, 84_532)])  # off-policy
    loop = AllocatorLoop(
        store=store,
        allocator=_AlwaysFirstAllocator(),
        goldsky=goldsky,
        onchain=onchain,
    )

    await loop.tick_once(now=now_ts())

    assert onchain.pending == []
    assert base_sid not in user.allocations
    events = store.recent_events(user.meta.user_address)
    assert not [
        e for e in events if e.kind in ("CROSS_CHAIN_ALLOCATION_DEFERRED", "ALLOCATION_CREATED")
    ]
