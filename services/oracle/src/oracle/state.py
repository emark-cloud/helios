"""In-memory snapshot state.

Holds a bounded ring of signed snapshots per asset. Two derived views:

  * `recent(asset, n)` — the last N snapshots (newest first).
  * `chain_root(asset, n)` — keccak256-chain over the last N snapshot
    digests. Phase 1's on-chain anchor (`Helios.sol` heartbeat or a
    standalone `OraclePriceAnchor`) commits this root every 5 min.
    Phase 2 swaps this for a Poseidon-chain so the momentum circuit can
    consume it directly without an extra hash-equivalence proof.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Lock

from eth_utils.crypto import keccak

from oracle.signer import LocalSigner


@dataclass(frozen=True, slots=True)
class Snapshot:
    asset: str
    price_e18: int
    timestamp_ms: int
    source: str
    digest: bytes
    signature: bytes
    signer: str


class SnapshotStore:
    def __init__(self, signer: LocalSigner, capacity_per_asset: int = 1024) -> None:
        if capacity_per_asset < 1:
            raise ValueError("capacity_per_asset must be >= 1")
        self._signer = signer
        self._capacity = capacity_per_asset
        self._rings: dict[str, deque[Snapshot]] = {}
        self._lock = Lock()

    def append(self, asset: str, price_e18: int, timestamp_ms: int, source: str) -> Snapshot:
        signed = self._signer.sign_quote(asset, price_e18, timestamp_ms)
        snap = Snapshot(
            asset=asset,
            price_e18=price_e18,
            timestamp_ms=timestamp_ms,
            source=source,
            digest=signed.digest,
            signature=signed.signature,
            signer=signed.signer,
        )
        with self._lock:
            ring = self._rings.get(asset)
            if ring is None:
                ring = deque(maxlen=self._capacity)
                self._rings[asset] = ring
            ring.append(snap)
        return snap

    def recent(self, asset: str, n: int) -> list[Snapshot]:
        if n < 1:
            raise ValueError("n must be >= 1")
        with self._lock:
            ring = self._rings.get(asset)
            if not ring:
                return []
            return list(ring)[-n:][::-1]  # newest first

    def chain_root(self, asset: str, n: int) -> bytes:
        """keccak256 chain over the last N digests (oldest → newest).

        Returns 32 zero bytes when no snapshots are present.
        """
        snaps = self.recent(asset, n)
        if not snaps:
            return b"\x00" * 32
        # Reverse to oldest-first for a deterministic chain.
        ordered = snaps[::-1]
        acc = ordered[0].digest
        for s in ordered[1:]:
            acc = keccak(acc + s.digest)
        return acc

    def assets(self) -> list[str]:
        with self._lock:
            return list(self._rings.keys())

    def head_timestamp_ms(self, asset: str) -> int | None:
        with self._lock:
            ring = self._rings.get(asset)
            if not ring:
                return None
            return ring[-1].timestamp_ms
