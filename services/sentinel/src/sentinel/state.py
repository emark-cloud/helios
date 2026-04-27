"""In-memory state Sentinel maintains between ticks.

Phase 1 keeps everything in process — Postgres persistence is a Phase 2
hardening task. The decision loop reads `users` (user → MetaStrategy +
allocator delegation), and `allocations` (user → strategy → live record
mirrored from `AllocatorVault.allocationOf` + StrategyVault NAV reads).

Two fanout queues exist:
  * `events` — append-only operational log streamed over `WS /v1/users/{user}/events`
  * `_event_subscribers` — set of asyncio.Queue per WS connection
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from threading import Lock
from typing import Literal

from helios_allocator.types import MetaStrategy

EventKind = Literal[
    "META_STRATEGY_SET",
    "ALLOCATION_CREATED",
    "ALLOCATION_INCREASED",
    "ALLOCATION_DECREASED",
    "STRATEGY_DEFUNDED",
    "REBALANCE_COMPLETE",
    "FEE_SETTLED",
]


@dataclass(frozen=True, slots=True)
class SentinelEvent:
    user_address: str
    kind: EventKind
    strategy_id: str | None
    amount_usd: int
    reason: str
    timestamp: int

    def to_dict(self) -> dict[str, object]:
        return {
            "user": self.user_address,
            "kind": self.kind,
            "strategy": self.strategy_id,
            "amount_usd": self.amount_usd,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


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

    @property
    def drawdown_bps(self) -> int:
        if self.high_water_mark_usd == 0 or self.nav_usd >= self.high_water_mark_usd:
            return 0
        delta = self.high_water_mark_usd - self.nav_usd
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


class SentinelStore:
    """Thread-safe wrapper around Sentinel's in-memory state."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._users: dict[str, UserState] = {}
        self._events: list[SentinelEvent] = []
        self._subscribers: dict[str, set[asyncio.Queue[SentinelEvent]]] = {}

    # ── Users ─────────────────────────────────────────────────
    def upsert_user(self, meta: MetaStrategy) -> UserState:
        with self._lock:
            existing = self._users.get(meta.user_address)
            if existing is None:
                state = UserState(meta=meta)
                self._users[meta.user_address] = state
                return state
            existing.meta = meta
            return existing

    def get_user(self, address: str) -> UserState | None:
        with self._lock:
            return self._users.get(address)

    def all_users(self) -> list[UserState]:
        with self._lock:
            return list(self._users.values())

    def replace_allocations(self, address: str, allocs: Iterable[AllocationState]) -> None:
        with self._lock:
            user = self._users.get(address)
            if user is None:
                return
            user.allocations = {a.strategy_id: a for a in allocs}

    def update_allocation(self, address: str, alloc: AllocationState) -> None:
        with self._lock:
            user = self._users.get(address)
            if user is None:
                return
            user.allocations[alloc.strategy_id] = alloc

    # ── Events ────────────────────────────────────────────────
    def emit_event(self, event: SentinelEvent) -> None:
        dead: list[asyncio.Queue[SentinelEvent]] = []
        with self._lock:
            self._events.append(event)
            queues = list(self._subscribers.get(event.user_address, set()))
        for q in queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q)
        if dead:
            with self._lock:
                subs = self._subscribers.get(event.user_address)
                if subs is not None:
                    for q in dead:
                        subs.discard(q)

    def recent_events(self, address: str, n: int = 50) -> list[SentinelEvent]:
        with self._lock:
            return [e for e in self._events if e.user_address == address][-n:]

    def subscribe(self, address: str) -> asyncio.Queue[SentinelEvent]:
        q: asyncio.Queue[SentinelEvent] = asyncio.Queue(maxsize=128)
        with self._lock:
            self._subscribers.setdefault(address, set()).add(q)
        return q

    def unsubscribe(self, address: str, q: asyncio.Queue[SentinelEvent]) -> None:
        with self._lock:
            subs = self._subscribers.get(address)
            if subs is not None:
                subs.discard(q)


def now_ts() -> int:
    return int(time.time())
