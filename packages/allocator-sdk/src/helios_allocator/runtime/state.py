"""In-memory state every allocator runtime maintains between ticks.

Phase 1 keeps everything in process — Postgres persistence is post-MVP.
The decision loop reads `users` (user → MetaStrategy + allocator
delegation) and `allocations` (user → strategy → live record mirrored
from `AllocatorVault.allocationOf` + StrategyVault NAV reads).

Two fanout queues exist:
  * `events` — append-only operational log streamed over
    `WS /v1/users/{user}/events`
  * `_event_subscribers` — set of asyncio.Queue per WS connection
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from threading import Lock
from typing import Literal

from helios_allocator.types import MetaStrategy

# Cap on the global event ring. `recent_events` returns at most 50
# per-user, so a 16k-entry ring covers ~hundreds of users at a few
# events per minute. The dashboard WS path pulls from `recent_events`,
# never the raw deque, so old entries fall off silently.
_EVENT_RING_CAP = 16_384

EventKind = Literal[
    "META_STRATEGY_SET",
    "ALLOCATION_CREATED",
    "ALLOCATION_INCREASED",
    "ALLOCATION_DECREASED",
    "STRATEGY_DEFUNDED",
    "REBALANCE_COMPLETE",
    "FEE_SETTLED",
    # Chain-observed events surfaced by `chain_watch.py` (Phase 4 WS-SVC-1).
    # The decision loop emits `STRATEGY_DEFUNDED` synchronously when it
    # submits a `defundStrategy` tx; the chain watcher independently
    # observes the on-chain `StrategyDefunded` log and would emit a
    # duplicate without `(tx_hash, kind, strategy)` dedup in
    # `AllocatorStore.emit_event`. The defund-trigger flow is chain-only
    # — the loop never observes the permissionless triggerDefund/
    # finalizeDefund cycle, so these kinds always originate from the
    # chain watcher.
    "DEFUND_TRIGGERED",
    "DEFUND_ARMED",
    "DEFUND_FINALIZED",
    "DEFUND_CANCELLED",
    "NAV_DIVERGENCE",
]


@dataclass(frozen=True, slots=True)
class AllocatorEvent:
    user_address: str
    kind: EventKind
    strategy_id: str | None
    amount_usd: int
    reason: str
    timestamp: int
    # Populated by chain-observed paths and by the decision loop after a
    # successful tx submission. Empty string elsewhere. Used by
    # `AllocatorStore.emit_event` for `(tx_hash, kind, strategy)` dedup
    # so the activity rail does not show two entries when the loop and
    # the chain watcher both emit for the same on-chain action.
    tx_hash: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "user": self.user_address,
            "kind": self.kind,
            "strategy": self.strategy_id,
            "amount_usd": self.amount_usd,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "tx_hash": self.tx_hash,
        }


# TWAP window for the drawdown defund decision (HIGH #14 in
# `docs/phase-3-review.md`). Five samples at the default 60s NAV-poll
# cadence ≈ 5 minutes — long enough to ride out a single bar's flash
# spike, short enough that a real drawdown still trips within the
# user's threshold before capital bleeds further. Display drawdown
# (`drawdown_bps`) keeps using the instant NAV so the dashboard
# remains reactive.
_NAV_TWAP_WINDOW = 5


@dataclass
class AllocationState:
    """Mirrored from on-chain reads each cycle.

    `capital_deployed_usd` matches `AllocationRecord.capitalDeployed`.
    `nav_usd` is read from `StrategyVault.navOf(allocatorVault)` prorated
    to the user's deployed share.
    """

    strategy_id: str
    chain_id: int
    declared_class: str
    capital_deployed_usd: int
    high_water_mark_usd: int
    nav_usd: int
    last_rebalance_ts: int = 0
    defunded: bool = False
    fees_paid_usd: int = 0
    # NAV history used by `twap_drawdown_bps`. Filled by `AllocatorStore`
    # on every `update_allocation`; not part of dataclass equality so
    # tests comparing states stay clean.
    nav_samples: deque[tuple[int, int]] = field(
        default_factory=lambda: deque(maxlen=_NAV_TWAP_WINDOW),
        init=False,
        repr=False,
        compare=False,
    )

    @property
    def drawdown_bps(self) -> int:
        if self.high_water_mark_usd == 0 or self.nav_usd >= self.high_water_mark_usd:
            return 0
        delta = self.high_water_mark_usd - self.nav_usd
        return (delta * 10_000) // self.high_water_mark_usd

    @property
    def twap_drawdown_bps(self) -> int:
        """Drawdown computed off the time-weighted-average NAV across
        the last `_NAV_TWAP_WINDOW` mirror reads. Used for defund
        decisions only — display still reads `drawdown_bps`. A single
        flash-crash bar cannot cross the threshold on its own; the
        window must agree."""
        if not self.nav_samples or self.high_water_mark_usd == 0:
            return 0
        twap = sum(n for _, n in self.nav_samples) // len(self.nav_samples)
        if twap >= self.high_water_mark_usd:
            return 0
        delta = self.high_water_mark_usd - twap
        return (delta * 10_000) // self.high_water_mark_usd


@dataclass
class UserState:
    meta: MetaStrategy
    delegated_capital_usd: int = 0
    allocations: dict[str, AllocationState] = field(default_factory=dict)
    last_rank_ts: int = 0
    last_rebalance_ts: int = 0
    realized_pnl_usd: int = 0
    fees_paid_usd: int = 0


class AllocatorStore:
    """Thread-safe wrapper around the runtime's in-memory state."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._users: dict[str, UserState] = {}
        self._events: deque[AllocatorEvent] = deque(maxlen=_EVENT_RING_CAP)
        self._subscribers: dict[str, set[asyncio.Queue[AllocatorEvent]]] = {}
        # Bounded dedup ring for `(tx_hash, kind, strategy_id)` keys.
        # Sized to comfortably exceed the chain watcher's per-cycle log
        # batch so cross-restart replays at the same checkpoint don't
        # double-emit. Entries with empty `tx_hash` skip the ring.
        self._dedup: deque[tuple[str, str, str | None]] = deque(maxlen=4_096)
        self._dedup_set: set[tuple[str, str, str | None]] = set()

    # ── Users ─────────────────────────────────────────────────
    # Addresses arrive in two casings: checksummed (frontend / wagmi
    # `signMessage` callers) and lowercase (chain logs decoded by the
    # chain watcher, websocket subscribers normalising before the
    # signature recovery). Storing under both casings would mean a POST
    # from the dashboard never matches the chain-watcher's later mirror
    # write. Normalise to lowercase at every key boundary so reads and
    # writes hash to the same slot regardless of source.
    @staticmethod
    def _k(address: str) -> str:
        return address.lower()

    def upsert_user(self, meta: MetaStrategy) -> UserState:
        with self._lock:
            key = self._k(meta.user_address)
            existing = self._users.get(key)
            if existing is None:
                state = UserState(meta=meta)
                self._users[key] = state
                return state
            existing.meta = meta
            return existing

    def get_user(self, address: str) -> UserState | None:
        with self._lock:
            return self._users.get(self._k(address))

    def all_users(self) -> list[UserState]:
        with self._lock:
            return list(self._users.values())

    def replace_allocations(self, address: str, allocs: Iterable[AllocationState]) -> None:
        with self._lock:
            user = self._users.get(self._k(address))
            if user is None:
                return
            ts = int(time.time())
            existing = user.allocations
            new_map: dict[str, AllocationState] = {}
            for a in allocs:
                prev = existing.get(a.strategy_id)
                if prev is not None:
                    a.nav_samples = prev.nav_samples
                a.nav_samples.append((ts, a.nav_usd))
                new_map[a.strategy_id] = a
            user.allocations = new_map

    def update_allocation(
        self, address: str, alloc: AllocationState, ts: int | None = None
    ) -> None:
        with self._lock:
            user = self._users.get(self._k(address))
            if user is None:
                return
            existing = user.allocations.get(alloc.strategy_id)
            if existing is not None:
                # Preserve the TWAP ring across mirror updates so
                # successive chain reads accumulate into the same
                # window — otherwise every poll resets to one sample.
                alloc.nav_samples = existing.nav_samples
            alloc.nav_samples.append((int(time.time()) if ts is None else ts, alloc.nav_usd))
            user.allocations[alloc.strategy_id] = alloc

    # ── Events ────────────────────────────────────────────────
    def emit_event(self, event: AllocatorEvent) -> None:
        dead: list[asyncio.Queue[AllocatorEvent]] = []
        with self._lock:
            if event.tx_hash:
                key = (event.tx_hash, event.kind, event.strategy_id)
                if key in self._dedup_set:
                    return
                if len(self._dedup) == self._dedup.maxlen:
                    self._dedup_set.discard(self._dedup[0])
                self._dedup.append(key)
                self._dedup_set.add(key)
            self._events.append(event)
            ev_key = self._k(event.user_address)
            queues = list(self._subscribers.get(ev_key, set()))
        for q in queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q)
        if dead:
            with self._lock:
                subs = self._subscribers.get(ev_key)
                if subs is not None:
                    for q in dead:
                        subs.discard(q)

    def recent_events(self, address: str, n: int = 50) -> list[AllocatorEvent]:
        key = self._k(address)
        with self._lock:
            return [e for e in self._events if self._k(e.user_address) == key][-n:]

    def subscribe(self, address: str) -> asyncio.Queue[AllocatorEvent]:
        q: asyncio.Queue[AllocatorEvent] = asyncio.Queue(maxsize=128)
        with self._lock:
            self._subscribers.setdefault(self._k(address), set()).add(q)
        return q

    def unsubscribe(self, address: str, q: asyncio.Queue[AllocatorEvent]) -> None:
        with self._lock:
            subs = self._subscribers.get(self._k(address))
            if subs is not None:
                subs.discard(q)


def now_ts() -> int:
    return int(time.time())
