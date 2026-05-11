"""Snapshot-window mirror tied to successful anchor commits.

Why this exists: `/v1/snapshots/recent` and `/v1/snapshots/root` used to
serve live snapshot-store state — whatever was in the ring at the
moment of the HTTP call. The on-chain `OraclePriceAnchor` commits a
Poseidon root over the *committed* snapshot window, which lags the
live ring by one bar in the steady state. With `ANCHOR_INTERVAL_BARS=1`
the gap is short but never zero: between strategy fetch and strategy
submit a new snapshot can land in the ring, so the strategy's locally-
recomputed root no longer matches anything the anchor has signed off
on. `StrategyVault.executeWithProof` then reverts `UnknownOracleRoot()`
on every trade.

Fix: after each successful `PriceAnchorScheduler` commit, record the
exact `(snapshots, root, window_end)` triple here. HTTP handlers read
from this mirror first so strategy + anchor see the same window. On
cold start (no commit yet for the asset) handlers fall through to the
live ring.

Thread-safe — Poller threads write via the scheduler, FastAPI handlers
read on the event loop. State is per-asset and overwritten on each new
commit; older commit windows are intentionally not retained (strategies
only need the latest committed root).
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from oracle.state import Snapshot


@dataclass(frozen=True, slots=True)
class CommittedWindow:
    """Snapshot window pinned to a successful on-chain commit.

    `snapshots` is newest-first to mirror `SnapshotStore.recent` so HTTP
    handlers can serve it directly. `root` is the BN254 field element
    (uint256) the anchor verified the signature against. `window_end_ms`
    is the timestamp of the newest snapshot (== the on-chain commit's
    `windowEnd`).
    """

    snapshots: list[Snapshot]
    root: int
    window_end_ms: int


class CommitMirror:
    def __init__(self) -> None:
        self._by_asset: dict[str, CommittedWindow] = {}
        self._lock = Lock()

    def record(
        self,
        asset: str,
        snapshots_newest_first: list[Snapshot],
        root: int,
        window_end_ms: int,
    ) -> None:
        """Replace the asset's committed window. Caller MUST only invoke
        after the on-chain `commit` tx mined successfully — otherwise
        strategies will fetch a root the contract never saw."""
        with self._lock:
            self._by_asset[asset] = CommittedWindow(
                snapshots=list(snapshots_newest_first),
                root=root,
                window_end_ms=window_end_ms,
            )

    def get(self, asset: str) -> CommittedWindow | None:
        with self._lock:
            return self._by_asset.get(asset)


__all__ = ["CommitMirror", "CommittedWindow"]
