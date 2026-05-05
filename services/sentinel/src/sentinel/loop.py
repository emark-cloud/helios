"""Sentinel decision loop — thin re-export of `helios_allocator.runtime.loop`.

WS1.A PR 2/3 — switch: the loop body lives in the SDK now. Sentinel
keeps the legacy import path (`sentinel.loop.SentinelLoop`) via an
alias so `service.py`, scenario scripts, and the test suite don't
churn. The `diff_allocations` symbol stays in `sentinel.allocator`
where the existing test imports it from; the SDK has its own private
copy inside the loop body.
"""

from __future__ import annotations

from helios_allocator.runtime.loop import (
    FEE_THRESHOLD_BPS,
    AllocatorLoop,
    LoopConfig,
)

# Legacy name preserved for service.py + test_loop.py.
SentinelLoop = AllocatorLoop

__all__ = [
    "FEE_THRESHOLD_BPS",
    "AllocatorLoop",
    "LoopConfig",
    "SentinelLoop",
]
