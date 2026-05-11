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
