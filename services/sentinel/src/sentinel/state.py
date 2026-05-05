"""Sentinel state — thin re-export of `helios_allocator.runtime.state`.

WS1.A PR 2/3 — switch: this module used to own the in-memory store and
event types. The implementation moved into the SDK so any allocator
service shares it; Sentinel keeps the legacy import path for
backwards-compat (FE WS payload schema, scenario fixtures, existing
tests). PR 3/3 may collapse this file once external consumers (scripts,
docs) have migrated.
"""

from __future__ import annotations

from helios_allocator.runtime.state import (
    AllocationState,
    AllocatorEvent,
    AllocatorStore,
    EventKind,
    SentinelEvent,
    SentinelStore,
    UserState,
    now_ts,
)

__all__ = [
    "AllocationState",
    "AllocatorEvent",
    "AllocatorStore",
    "EventKind",
    "SentinelEvent",
    "SentinelStore",
    "UserState",
    "now_ts",
]
