"""Sentinel Goldsky client — thin re-export of `helios_allocator.runtime.goldsky`.

WS1.A PR 2/3 — switch: implementation moved into the SDK. Legacy names
preserved: `SentinelGoldsky` aliases `AllocatorGoldsky`, and the
underscore-prefixed `_to_candidate` is preserved alongside the public
`to_candidate` because the loop test suite imports the underscore form.
"""

from __future__ import annotations

from helios_allocator.runtime.goldsky import (
    AllocatorGoldsky,
    StrategyDirectoryRow,
    to_candidate,
)

# Legacy names — kept for tests + scenario imports.
SentinelGoldsky = AllocatorGoldsky
_to_candidate = to_candidate

__all__ = [
    "AllocatorGoldsky",
    "SentinelGoldsky",
    "StrategyDirectoryRow",
    "_to_candidate",
    "to_candidate",
]
