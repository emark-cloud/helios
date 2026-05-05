"""Smoke tests for the SDK's in-memory store + event types.

WS1.A PR 1/3 — these mirror the equivalent sentinel-side coverage so the
PR 2/3 cutover (sentinel switching to the SDK paths) is a no-op for
downstream behavior. The full parity replay against `services/sentinel`
fixtures lives in PR 2/3's test suite.
"""

from __future__ import annotations

import asyncio

import pytest
from helios_allocator.runtime.state import (
    AllocationState,
    AllocatorEvent,
    AllocatorStore,
    SentinelEvent,
    SentinelStore,
    UserState,
    now_ts,
)
from helios_allocator.types import MetaStrategy


def _meta(addr: str = "0x" + "ab" * 20) -> MetaStrategy:
    return MetaStrategy(
        user_address=addr,
        allowed_strategy_classes=("momentum_v1",),
        allowed_assets=("USDC",),
        allowed_chains=(2368,),
        max_capital_usd=10_000,
        max_per_strategy_bps=5_000,
        max_strategies_count=2,
        drawdown_threshold_bps=1_500,
        max_fee_rate_bps=2_500,
        rebalance_cadence_sec=900,
        valid_until=2_000_000_000,
    )


def test_event_aliases_match() -> None:
    """`SentinelEvent` is preserved as a back-compat alias for `AllocatorEvent`."""
    assert SentinelEvent is AllocatorEvent
    assert SentinelStore is AllocatorStore


def test_drawdown_bps_computation() -> None:
    a = AllocationState(
        strategy_id="0x" + "11" * 20,
        chain_id=2368,
        declared_class="momentum_v1",
        capital_deployed_usd=1_000,
        high_water_mark_usd=1_000,
        nav_usd=850,
    )
    assert a.drawdown_bps == 1_500  # 15% drawdown

    a.nav_usd = 1_100
    assert a.drawdown_bps == 0  # NAV above HWM

    a.high_water_mark_usd = 0
    assert a.drawdown_bps == 0  # uninitialized HWM


def test_store_upsert_and_lookup() -> None:
    store = AllocatorStore()
    user = store.upsert_user(_meta())
    assert isinstance(user, UserState)
    assert store.get_user(user.meta.user_address) is user
    assert store.all_users() == [user]

    # Idempotent re-upsert mutates the existing record, not creating a duplicate.
    refreshed = store.upsert_user(_meta())
    assert refreshed is user
    assert len(store.all_users()) == 1


def test_event_emit_and_recent() -> None:
    store = AllocatorStore()
    addr = "0x" + "cd" * 20
    store.upsert_user(_meta(addr))
    ev = AllocatorEvent(
        user_address=addr,
        kind="ALLOCATION_CREATED",
        strategy_id="0x" + "11" * 20,
        amount_usd=1_000,
        reason="first",
        timestamp=now_ts(),
    )
    store.emit_event(ev)
    assert store.recent_events(addr) == [ev]
    assert store.recent_events("0x" + "ff" * 20) == []


def test_event_dict_shape() -> None:
    ev = AllocatorEvent(
        user_address="0x" + "ab" * 20,
        kind="FEE_SETTLED",
        strategy_id=None,
        amount_usd=42,
        reason="HWM_BREACH",
        timestamp=1_000_000,
    )
    payload = ev.to_dict()
    assert payload == {
        "user": "0x" + "ab" * 20,
        "kind": "FEE_SETTLED",
        "strategy": None,
        "amount_usd": 42,
        "reason": "HWM_BREACH",
        "timestamp": 1_000_000,
    }


@pytest.mark.asyncio
async def test_subscribe_receives_events() -> None:
    store = AllocatorStore()
    addr = "0x" + "ef" * 20
    store.upsert_user(_meta(addr))
    queue = store.subscribe(addr)
    ev = AllocatorEvent(
        user_address=addr,
        kind="REBALANCE_COMPLETE",
        strategy_id=None,
        amount_usd=100,
        reason="",
        timestamp=now_ts(),
    )
    store.emit_event(ev)
    received = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert received == ev
    store.unsubscribe(addr, queue)
