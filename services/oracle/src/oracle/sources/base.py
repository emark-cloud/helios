"""Price-source protocol.

The oracle service composes one or more `PriceSource` implementations,
calling `fetch(asset)` per polling tick. The first source that returns a
quote wins; subsequent sources are tried only on `SourceError`. Sources
must be stateless and thread-safe — state lives in `oracle.state`.

Phase 2 (`algebra.py`) plugs in a TWAP read against an on-chain DEX once
Kite testnet has one; the rest of the service does not change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PriceQuote:
    """One spot price observation.

    `price_e18` is the price quoted in the asset's quote currency, scaled
    to 18 decimals (matches the on-chain fixed-point convention used by
    `momentum_v1.circom`'s `min_amount_out` math).
    """

    asset: str
    price_e18: int
    timestamp_ms: int
    source: str


class SourceError(Exception):
    """Raised when a source can't return a quote (network, rate-limit, asset unsupported)."""


class PriceSource(Protocol):
    """Async price source. Implementations live in `oracle.sources.<name>`."""

    name: str

    async def fetch(self, asset: str) -> PriceQuote:
        """Return the latest quote for `asset` or raise `SourceError`."""
        ...
