"""AllocatorSDK runtime — the plumbing every allocator service shares.

Public surface:

    AllocatorRuntime  — composes store / loop / onchain / goldsky into
                        one object an allocator service boots from.
    AllocatorLoop     — accepts any BaseAllocator subclass and runs the
                        six-step decision cycle (Helios.md §11.2).
    AllocatorOnChain  — tx-submission + on-chain reads, with
                        `register_allocator` for first-time bootstrap on
                        AllocatorRegistry.
    AllocatorGoldsky  — strategy directory + reputation reads.
    AllocatorStore    — in-memory user / allocation / event store.
    AllocatorEvent    — dashboard event surface.
"""

from __future__ import annotations

from helios_allocator.runtime.goldsky import (
    AllocatorGoldsky,
    MultiChainAllocatorGoldsky,
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
    "MultiChainAllocatorGoldsky",
    "OnChainCall",
    "StrategyDirectoryRow",
    "UserState",
    "now_ts",
    "to_candidate",
]
