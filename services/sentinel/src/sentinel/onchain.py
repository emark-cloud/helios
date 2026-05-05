"""Sentinel on-chain client — thin re-export of `helios_allocator.runtime.onchain`.

WS1.A PR 2/3 — switch: the implementation lives in the SDK. Sentinel
preserves its legacy import path (`sentinel.onchain.OnChainRunner`) via
the `OnChainRunner = AllocatorOnChain` alias so test fixtures and
scenario code keep working. PR 3/3 will retire the legacy name.
"""

from __future__ import annotations

from helios_allocator.runtime.onchain import AllocatorOnChain, OnChainCall

# Legacy name preserved for tests + scripts that imported `OnChainRunner`.
OnChainRunner = AllocatorOnChain

__all__ = ["AllocatorOnChain", "OnChainCall", "OnChainRunner"]
