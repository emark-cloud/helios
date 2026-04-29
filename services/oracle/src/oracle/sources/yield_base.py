"""Yield-source protocol.

Mirrors `oracle.sources.base` for APY feeds. Phase 2 ships scripted
stubs (`yield_aave_stub`, `yield_compound_stub`) so `yield_rotation_v1`
has a yield differential to chase in scenario mode; Phase 5 swaps in
real on-chain reads against Aave v3 / Compound v3 reserve data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class YieldQuote:
    """One APY observation for a lending market.

    `apy_bps_e6` is APY in basis-points scaled to 1e6 — i.e. one unit is
    `1e-10` of supply rate. 5.25% APY → `52_500 * 1e6 = 52_500_000_000`.
    Wait — 5.25% = 525 bps; with the 1e6 scale that is `525_000_000`.
    Holding to 1e6 gives 4 decimals of bp precision and keeps everything
    inside int64.
    """

    market_id: str
    apy_bps_e6: int
    timestamp_ms: int
    source: str


class YieldSourceError(Exception):
    """Raised when a yield source can't return a quote."""


class YieldSource(Protocol):
    name: str

    async def fetch(self, market_id: str) -> YieldQuote: ...
