"""AllocatorSDK runtime — the plumbing every allocator service shares.

WS1.A PR 1/3 — extract: this module tree is a parallel implementation of
what `services/sentinel/` ships today. Sentinel keeps importing from its
own paths in this PR; PR 2/3 flips Sentinel's imports to consume from
here, and PR 3/3 deletes the legacy paths.

Public surface:

    AllocatorRuntime  — composes store / loop / onchain / goldsky into
                        one object an allocator service boots from.
    AllocatorLoop     — generalized SentinelLoop. Accepts any BaseAllocator
                        subclass; `services/helix/` and any third-party
                        allocator wires its own subclass into the loop.
    AllocatorOnChain  — tx-submission + on-chain reads. Adds
                        `register_allocator` for first-time bootstrap on
                        AllocatorRegistry.
    AllocatorGoldsky  — strategy directory + reputation reads.
    AllocatorStore    — in-memory user / allocation / event store.
    AllocatorEvent    — dashboard event surface (back-compat alias
                        `SentinelEvent` re-exported).
"""

from __future__ import annotations

from helios_allocator.runtime.goldsky import (
    AllocatorGoldsky,
    StrategyDirectoryRow,
    to_candidate,
)
from helios_allocator.runtime.loop import AllocatorLoop, LoopConfig
from helios_allocator.runtime.onchain import AllocatorOnChain, OnChainCall
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
    "AllocatorGoldsky",
    "AllocatorLoop",
    "AllocatorOnChain",
    "AllocatorStore",
    "EventKind",
    "LoopConfig",
    "OnChainCall",
    "SentinelEvent",
    "SentinelStore",
    "StrategyDirectoryRow",
    "UserState",
    "now_ts",
    "to_candidate",
]
