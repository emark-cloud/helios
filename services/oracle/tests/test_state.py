"""Snapshot store: ring semantics + chain root."""

from __future__ import annotations

from eth_utils.crypto import keccak
from oracle.signer import LocalSigner
from oracle.state import SnapshotStore


def _store() -> SnapshotStore:
    return SnapshotStore(signer=LocalSigner(""), capacity_per_asset=4)


def test_recent_returns_newest_first() -> None:
    s = _store()
    for i in range(3):
        s.append("KITE/USDT", price_e18=10**18 + i, timestamp_ms=1000 + i, source="test")
    snaps = s.recent("KITE/USDT", 16)
    assert [x.timestamp_ms for x in snaps] == [1002, 1001, 1000]


def test_ring_capacity_evicts_oldest() -> None:
    s = _store()
    for i in range(10):
        s.append("KITE/USDT", price_e18=10**18 + i, timestamp_ms=1000 + i, source="test")
    snaps = s.recent("KITE/USDT", 16)
    # capacity_per_asset=4 → only the last 4 survive (1006..1009).
    assert [x.timestamp_ms for x in snaps] == [1009, 1008, 1007, 1006]


def test_chain_root_matches_keccak_chain() -> None:
    s = _store()
    appended = [
        s.append("KITE/USDT", price_e18=10**18 + i, timestamp_ms=1000 + i, source="test")
        for i in range(3)
    ]
    expected = appended[0].digest
    expected = keccak(expected + appended[1].digest)
    expected = keccak(expected + appended[2].digest)
    assert s.chain_root("KITE/USDT", 3) == expected


def test_chain_root_empty_returns_zero() -> None:
    s = _store()
    assert s.chain_root("KITE/USDT", 16) == b"\x00" * 32


def test_chain_root_truncates_to_n() -> None:
    s = _store()
    for i in range(4):
        s.append("KITE/USDT", price_e18=10**18 + i, timestamp_ms=1000 + i, source="test")
    # Asking for n=2 should chain only the last two, not all four.
    last_two = s.recent("KITE/USDT", 2)
    a, b = last_two[1].digest, last_two[0].digest  # oldest, newest
    expected = keccak(a + b)
    assert s.chain_root("KITE/USDT", 2) == expected
