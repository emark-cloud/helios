"""Snapshot store: ring semantics + Poseidon chain root."""

from __future__ import annotations

from oracle.poseidon import poseidon_chain
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


def test_chain_root_matches_circuit_poseidon_chain() -> None:
    s = _store()
    prices = [10**18 + i for i in range(3)]
    for i, p in enumerate(prices):
        s.append("KITE/USDT", price_e18=p, timestamp_ms=1000 + i, source="test")
    # Oldest → newest, exactly as the circuit consumes price_observations.
    expected = poseidon_chain(prices)
    assert s.chain_root("KITE/USDT", 3) == expected


def test_chain_root_empty_returns_zero() -> None:
    s = _store()
    assert s.chain_root("KITE/USDT", 16) == 0


def test_chain_root_truncates_to_n() -> None:
    s = _store()
    prices = [10**18 + i for i in range(4)]
    for i, p in enumerate(prices):
        s.append("KITE/USDT", price_e18=p, timestamp_ms=1000 + i, source="test")
    # Asking for n=2 should chain only the last two (oldest-first), not all four.
    expected = poseidon_chain(prices[-2:])
    assert s.chain_root("KITE/USDT", 2) == expected


def test_chain_root_returns_field_element() -> None:
    s = _store()
    s.append("KITE/USDT", price_e18=10**18, timestamp_ms=1000, source="test")
    root = s.chain_root("KITE/USDT", 1)
    assert isinstance(root, int)
    # BN254 scalar field. Any valid Poseidon output fits in 32 bytes unsigned.
    assert 0 <= root < (1 << 254)
