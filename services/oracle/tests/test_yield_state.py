"""Yield ring buffer + Poseidon chain root."""

from __future__ import annotations

from oracle.poseidon import poseidon_chain
from oracle.signer import LocalSigner
from oracle.yield_state import YieldStore


def _store() -> YieldStore:
    return YieldStore(signer=LocalSigner(""), capacity_per_market=4)


def test_recent_returns_newest_first() -> None:
    s = _store()
    for i in range(3):
        s.append("aave-v3:USDC", apy_bps_e6=500_000_000 + i, timestamp_ms=1000 + i, source="stub")
    snaps = s.recent("aave-v3:USDC", 16)
    assert [x.timestamp_ms for x in snaps] == [1002, 1001, 1000]


def test_ring_capacity_evicts_oldest() -> None:
    s = _store()
    for i in range(10):
        s.append("aave-v3:USDC", apy_bps_e6=500_000_000 + i, timestamp_ms=1000 + i, source="stub")
    snaps = s.recent("aave-v3:USDC", 16)
    assert [x.timestamp_ms for x in snaps] == [1009, 1008, 1007, 1006]


def test_chain_root_matches_poseidon_chain() -> None:
    s = _store()
    apys = [500_000_000, 502_000_000, 498_000_000]
    for i, apy in enumerate(apys):
        s.append("aave-v3:USDC", apy_bps_e6=apy, timestamp_ms=1000 + i, source="stub")
    expected = poseidon_chain(apys)
    assert s.chain_root("aave-v3:USDC", 3) == expected


def test_chain_root_empty_returns_zero() -> None:
    s = _store()
    assert s.chain_root("aave-v3:USDC", 16) == 0


def test_chain_root_truncates_to_n() -> None:
    s = _store()
    apys = [500_000_000, 510_000_000, 520_000_000, 530_000_000]
    for i, apy in enumerate(apys):
        s.append("aave-v3:USDC", apy_bps_e6=apy, timestamp_ms=1000 + i, source="stub")
    expected = poseidon_chain(apys[-2:])
    assert s.chain_root("aave-v3:USDC", 2) == expected


def test_two_markets_isolated() -> None:
    s = _store()
    s.append("aave-v3:USDC", apy_bps_e6=500_000_000, timestamp_ms=1000, source="stub")
    s.append("compound-v3:USDC", apy_bps_e6=510_000_000, timestamp_ms=1000, source="stub")
    assert set(s.markets()) == {"aave-v3:USDC", "compound-v3:USDC"}
    assert s.chain_root("aave-v3:USDC", 1) == poseidon_chain([500_000_000])
    assert s.chain_root("compound-v3:USDC", 1) == poseidon_chain([510_000_000])
