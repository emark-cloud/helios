"""Public types exposed to yield-rotation strategy operators.

`yield_rotation_v1` is structurally distinct from the directional
strategy classes — there's no asset-pair swap, no slippage, no per-bar
price observations. The strategy fires on *yield* updates: an APY
differential between two allowlisted lending markets.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class YieldTick:
    """A single APY observation for a market.

    Mirrors `oracle.yield_state.YieldSnapshot` minus the signature bytes
    — the strategy doesn't verify oracle signatures locally; that's the
    on-chain anchor's job.
    """

    market_id: int
    """Stable, registry-assigned market identifier (uint64). Both the
    yield Merkle tree and the allowlist tree key on this id."""

    apy_bps_e6: int
    """APY in basis-points × 1e6 (so 5.25% APY = 525_000_000)."""

    timestamp_ms: int


@dataclass(frozen=True, slots=True)
class RotationIntent:
    """The operator's intent to rotate capital between two markets.

    The witness builder turns this into a YR-circuit-shaped payload.
    Distinct from `helios.types.TradeIntent` because the field set is
    different (no asset-in/out, no slippage, no direction enum).
    """

    m_from: int
    m_to: int
    amount_in_usd: float
    apy_from_bps: int
    apy_to_bps: int

    def __post_init__(self) -> None:
        if self.m_from == self.m_to:
            raise ValueError("rotation must change markets")
        if self.amount_in_usd <= 0:
            raise ValueError("rotation amount must be positive")
