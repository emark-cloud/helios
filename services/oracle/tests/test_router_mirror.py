"""Smoke tests for `RouterPriceMirror` in dry-run mode.

The math is locked down by `test_router_mirror_math.py`; these tests
cover the wiring: pair lookup, snapshot reading, dry-run audit-ring
behavior, and the no-op paths (unknown asset, empty store).
"""

from __future__ import annotations

import asyncio

import pytest
from oracle.router_mirror import PairSpec, RouterPriceMirror
from oracle.router_mirror_math import compute_price_pair
from oracle.service import _compose_on_snapshot
from oracle.signer import LocalSigner
from oracle.state import SnapshotStore


def _store_with(asset: str, price_e18: int, ts_ms: int = 1_000) -> SnapshotStore:
    store = SnapshotStore(signer=LocalSigner(""))
    store.append(asset=asset, price_e18=price_e18, timestamp_ms=ts_ms, source="test")
    return store


def _eth_pair(usdc: str = "0x" + "11" * 20, weth: str = "0x" + "22" * 20) -> PairSpec:
    return PairSpec(
        oracle_asset="ETH/USDT",
        stable_address=usdc,
        stable_decimals=6,
        asset_address=weth,
        asset_decimals=18,
    )


def _mirror(store: SnapshotStore, pair: PairSpec) -> RouterPriceMirror:
    # Empty rpc/signer/router → dry-run (gated by `live`).
    return RouterPriceMirror(
        store=store,
        rpc_url="",
        signer_pk="",
        router_address="",
        chain_id=2368,
        pairs=[pair],
    )


def test_dry_run_records_both_directions() -> None:
    pair = _eth_pair()
    store = _store_with(pair.oracle_asset, 3_000 * 10**18)
    mirror = _mirror(store, pair)

    rec = mirror.on_snapshot(pair.oracle_asset)
    assert rec is not None
    assert not rec.submitted  # dry-run path doesn't submit
    assert rec.error == ""
    # The recorded (num, denom) pairs must match the converter output.
    s2a, a2s = compute_price_pair(price_e18=3_000 * 10**18, decimals_stable=6, decimals_asset=18)
    assert (rec.s2a_num, rec.s2a_denom) == s2a
    assert (rec.a2s_num, rec.a2s_denom) == a2s
    # Audit ring sees one entry.
    assert len(mirror.pending) == 1


def test_unknown_asset_is_noop() -> None:
    pair = _eth_pair()
    store = _store_with(pair.oracle_asset, 3_000 * 10**18)
    mirror = _mirror(store, pair)
    assert mirror.on_snapshot("BTC/USDT") is None
    assert len(mirror.pending) == 0


def test_empty_store_is_noop() -> None:
    pair = _eth_pair()
    # Store has no snapshots for the configured asset.
    store = SnapshotStore(signer=LocalSigner(""))
    mirror = _mirror(store, pair)
    assert mirror.on_snapshot(pair.oracle_asset) is None
    assert len(mirror.pending) == 0


def test_multiple_pairs_indexed_independently() -> None:
    eth = _eth_pair(weth="0x" + "33" * 20)
    btc = PairSpec(
        oracle_asset="BTC/USDT",
        stable_address="0x" + "11" * 20,
        stable_decimals=6,
        asset_address="0x" + "44" * 20,
        asset_decimals=8,
    )
    store = SnapshotStore(signer=LocalSigner(""))
    store.append("ETH/USDT", 3_000 * 10**18, 1_000, "test")
    store.append("BTC/USDT", 50_000 * 10**18, 1_000, "test")

    mirror = RouterPriceMirror(
        store=store,
        rpc_url="",
        signer_pk="",
        router_address="",
        chain_id=2368,
        pairs=[eth, btc],
    )
    eth_rec = mirror.on_snapshot("ETH/USDT")
    btc_rec = mirror.on_snapshot("BTC/USDT")
    assert eth_rec is not None
    assert btc_rec is not None
    assert eth_rec.price_e18 == 3_000 * 10**18
    assert btc_rec.price_e18 == 50_000 * 10**18


@pytest.mark.asyncio
async def test_async_entry_point_matches_sync() -> None:
    pair = _eth_pair()
    store = _store_with(pair.oracle_asset, 3_000 * 10**18)
    mirror = _mirror(store, pair)
    rec = await mirror.on_snapshot_async(pair.oracle_asset)
    assert rec is not None
    assert not rec.submitted
    assert (rec.s2a_num, rec.s2a_denom) == compute_price_pair(
        price_e18=3_000 * 10**18, decimals_stable=6, decimals_asset=18
    )[0]


def test_zero_price_is_logged_not_raised() -> None:
    pair = _eth_pair()
    # price_e18=0 is invalid for the converter; the keeper should swallow
    # the error and return None rather than crash the Poller callback.
    store = SnapshotStore(signer=LocalSigner(""))
    store.append(pair.oracle_asset, 0, 1_000, "test")
    mirror = _mirror(store, pair)
    assert mirror.on_snapshot(pair.oracle_asset) is None


def test_live_property_gates_correctly() -> None:
    pair = _eth_pair()
    store = _store_with(pair.oracle_asset, 3_000 * 10**18)
    # All three blank → not live.
    assert _mirror(store, pair).live is False
    # Any one blank → still not live.
    partial = RouterPriceMirror(
        store=store,
        rpc_url="http://x",
        signer_pk="",
        router_address="",
        chain_id=2368,
        pairs=[pair],
    )
    assert partial.live is False
    # All three set → live.
    fully = RouterPriceMirror(
        store=store,
        rpc_url="http://x",
        signer_pk="0x" + "11" * 32,
        router_address="0x" + "22" * 20,
        chain_id=2368,
        pairs=[pair],
    )
    assert fully.live is True


def test_compose_on_snapshot_calls_both() -> None:
    """Sanity check the service-level fan-out: when both consumers are
    wired, both run per snapshot."""
    calls: list[str] = []

    class FakeScheduler:
        async def on_bar_async(self, asset: str) -> None:
            calls.append(f"sched:{asset}")

    pair = _eth_pair()
    store = _store_with(pair.oracle_asset, 3_000 * 10**18)
    mirror = _mirror(store, pair)
    composed = _compose_on_snapshot(FakeScheduler(), mirror)  # type: ignore[arg-type]

    asyncio.run(composed("ETH/USDT"))
    assert "sched:ETH/USDT" in calls
    # Mirror ran too (audit ring picked up the entry).
    assert len(mirror.pending) == 1
