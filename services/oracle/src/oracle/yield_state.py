"""Yield-snapshot state — APY observations per market.

Mirrors `oracle.state` but keyed by `market_id` (e.g. `aave-v3:USDC`,
`compound-v3:USDC`) rather than asset symbol. Each snapshot stores an
APY in basis-points scaled to 1e6 (`apy_bps_e6`) so 5.25% APY is
`5_250_000` — gives 4 decimal places of precision while staying in
uint64 range.

`yield_rotation_v1.circom` (WS1.C) consumes the chained Poseidon root
of the last N APY observations as its public `yield_oracle_root`; the
oracle commits this root to `OracleYieldAnchor` so the on-chain
verifier path is closed. Phase 5 swaps the stub feeders for real Aave/
Compound integrations; the chain semantics here are the same as the
production shape, only the source is mocked.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Lock

from oracle.poseidon import poseidon_chain
from oracle.signer import LocalSigner


@dataclass(frozen=True, slots=True)
class YieldSnapshot:
    market_id: str
    apy_bps_e6: int
    timestamp_ms: int
    source: str
    digest: bytes
    signature: bytes
    signer: str


class YieldStore:
    def __init__(self, signer: LocalSigner, capacity_per_market: int = 1024) -> None:
        if capacity_per_market < 1:
            raise ValueError("capacity_per_market must be >= 1")
        self._signer = signer
        self._capacity = capacity_per_market
        self._rings: dict[str, deque[YieldSnapshot]] = {}
        self._lock = Lock()

    def append(
        self, market_id: str, apy_bps_e6: int, timestamp_ms: int, source: str
    ) -> YieldSnapshot:
        # Reuse the price signer's `sign_quote` shape — same EIP-191 framing,
        # different payload semantics. `market_id` is hashed in place of the
        # asset symbol; `apy_bps_e6` rides the `price_e18` slot.
        signed = self._signer.sign_quote(market_id, apy_bps_e6, timestamp_ms)
        snap = YieldSnapshot(
            market_id=market_id,
            apy_bps_e6=apy_bps_e6,
            timestamp_ms=timestamp_ms,
            source=source,
            digest=signed.digest,
            signature=signed.signature,
            signer=signed.signer,
        )
        with self._lock:
            ring = self._rings.get(market_id)
            if ring is None:
                ring = deque(maxlen=self._capacity)
                self._rings[market_id] = ring
            ring.append(snap)
        return snap

    def recent(self, market_id: str, n: int) -> list[YieldSnapshot]:
        if n < 1:
            raise ValueError("n must be >= 1")
        with self._lock:
            ring = self._rings.get(market_id)
            if not ring:
                return []
            return list(ring)[-n:][::-1]  # newest first

    def chain_root(self, market_id: str, n: int) -> int:
        """Poseidon chain over the last N APY observations (oldest → newest)."""
        snaps = self.recent(market_id, n)
        if not snaps:
            return 0
        ordered = snaps[::-1]
        return poseidon_chain([s.apy_bps_e6 for s in ordered])

    def markets(self) -> list[str]:
        with self._lock:
            return list(self._rings.keys())

    def head_timestamp_ms(self, market_id: str) -> int | None:
        with self._lock:
            ring = self._rings.get(market_id)
            if not ring:
                return None
            return ring[-1].timestamp_ms
