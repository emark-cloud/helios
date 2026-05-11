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


def _row(sid: str) -> StrategyDirectoryRow:
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
