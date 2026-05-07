"""Smoke tests for the SDK's in-memory store + event types."""

from __future__ import annotations

import asyncio

import pytest
from helios_allocator.runtime.state import (
    AllocationState,
    AllocatorEvent,
    AllocatorStore,
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


def test_twap_drawdown_smooths_flash_spike() -> None:
    """HIGH #14 — a single bar where NAV drops 30% must NOT trip a 15%
    drawdown threshold once the surrounding samples agree NAV is fine.
    The instant `drawdown_bps` does see the spike (used for display);
    `twap_drawdown_bps` averages over the window so defund decisions
    aren't held hostage to a single bad oracle bar."""
    a = AllocationState(
        strategy_id="0x" + "11" * 20,
        chain_id=2368,
        declared_class="momentum_v1",
        capital_deployed_usd=1_000,
        high_water_mark_usd=1_000,
        nav_usd=700,  # the flash bar
    )
    # Four healthy samples + the current spike. Mean = (1000*4 + 700) / 5 = 940 ⇒ 6% twap dd.
    for ts, nav in [(1, 1_000), (2, 1_000), (3, 1_000), (4, 1_000)]:
        a.nav_samples.append((ts, nav))
    a.nav_samples.append((5, 700))
    assert a.drawdown_bps == 3_000  # instant view sees the spike
    assert a.twap_drawdown_bps == 600  # smoothed view does not


def test_twap_drawdown_with_no_samples_falls_back_to_zero() -> None:
    a = AllocationState(
        strategy_id="0x" + "11" * 20,
        chain_id=2368,
        declared_class="momentum_v1",
        capital_deployed_usd=1_000,
        high_water_mark_usd=1_000,
        nav_usd=600,
    )
    # No samples populated yet — twap returns 0 so a fresh allocation
    # never gets defunded on its first tick before the ring fills.
    assert a.twap_drawdown_bps == 0


def test_update_allocation_carries_nav_samples_forward() -> None:
    """Successive chain mirrors must accumulate into the same TWAP ring,
    not reset it — otherwise a one-mirror window can never include enough
    history to smooth a flash bar."""
    store = AllocatorStore()
    user = store.upsert_user(_meta())
    sid = "0x" + "11" * 20
    for i, nav in enumerate([1_000, 1_000, 1_000, 700], start=1):
        a = AllocationState(
            strategy_id=sid,
            chain_id=2368,
            declared_class="momentum_v1",
            capital_deployed_usd=1_000,
            high_water_mark_usd=1_000,
            nav_usd=nav,
        )
        store.update_allocation(user.meta.user_address, a, ts=i)

    final = store.get_user(user.meta.user_address).allocations[sid]  # type: ignore[union-attr]
    assert [n for _, n in final.nav_samples] == [1_000, 1_000, 1_000, 700]
    # Mean = 925 ⇒ 7.5% drawdown (well below a 15% threshold).
    assert final.twap_drawdown_bps == 750


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
        "tx_hash": "",
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
