"""Algebra Integral DEX TWAP source — Phase 2 stub.

Kite testnet has no documented Algebra deployment as of 2026-04-25
(`memory/reference_kite_contract_surface.md`). When that lands, this
source will read the pool's accumulator and derive a TWAP-from-N-blocks
quote — same `PriceSource` interface, no other code changes.

Defined here so the source-abstraction shape is stable from Phase 1.
"""

from __future__ import annotations

from oracle.sources.base import PriceQuote, SourceError


class AlgebraSource:
    name = "algebra"

    def __init__(self) -> None:
        raise NotImplementedError(
            "AlgebraSource lands in Phase 2 once Kite testnet has Algebra Integral. "
            "Use BinanceSource + CoingeckoSource for Phase 1."
        )

    async def fetch(self, asset: str) -> PriceQuote:
        raise SourceError(f"algebra: phase 2 stub (asked for {asset!r})")
