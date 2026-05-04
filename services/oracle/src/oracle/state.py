"""In-memory snapshot state.

Holds a bounded ring of signed snapshots per asset. Two derived views:

  * `recent(asset, n)` — the last N snapshots (newest first).
  * `chain_root(asset, n)` — Poseidon-chain over the last N raw prices,
    bit-exact with the chained-Poseidon commitment in
    `momentum_v1.circom` and the mean-reversion / yield-rotation
    circuits to come. The same root that gets committed to
    `OraclePriceAnchor` is what each circuit verifies as the public
    `oracle_root` input — no extra hash-equivalence proof needed.

Phase 1 chained over keccak(digest_bytes); Phase 2 chains Poseidon over
price field elements directly.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Lock

from oracle.poseidon import poseidon_chain
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

    def chain_root(self, asset: str, n: int) -> int:
        """Poseidon chain over the last N price_e18 (oldest → newest).

        Shape: h0 = P(p0); hi = P(h_{i-1}, pi). Returns 0 when no
        snapshots are present (a sentinel `oracle_root` that no honest
        witness will produce — Poseidon of any nonzero input has
        negligible probability of being 0).
        """
        _, root = self.snapshot_window(asset, n)
        return root

    def snapshot_window(self, asset: str, n: int) -> tuple[list[Snapshot], int]:
        """Atomic `(recent, chain_root)` over the same N snapshots.

        `recent()` and `chain_root()` taken separately race with `append()`
        — a poller insertion between the two locked calls produces a
        committed Poseidon root that doesn't match the snapshots the caller
        held. The on-chain commit cadence in `PriceAnchorScheduler` calls
        this single method so the committed `(window, root)` pair is
        always self-consistent.
        """
        if n < 1:
            raise ValueError("n must be >= 1")
        with self._lock:
            ring = self._rings.get(asset)
            if not ring:
                return [], 0
            snaps_newest_first = list(ring)[-n:][::-1]
        ordered = snaps_newest_first[::-1]  # oldest-first for the circuit chain
        root = poseidon_chain([s.price_e18 for s in ordered])
        return snaps_newest_first, root

    def assets(self) -> list[str]:
        with self._lock:
            return list(self._rings.keys())

    def head_timestamp_ms(self, asset: str) -> int | None:
        with self._lock:
            ring = self._rings.get(asset)
            if not ring:
                return None
            return ring[-1].timestamp_ms
