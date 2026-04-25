"""StrategyAgent base class.

Phase 0 ships the abstract surface so service code can import it. Phase 1
backfills the concrete behavior:
  - market data polling (1-minute bars)
  - calling `on_bar(asset, snapshot)` per asset per bar
  - constructing trade calldata for the chosen DEX router
  - bundling witness data and POSTing to the Prover Service
  - submitting `executeWithProof` with proper gas handling
  - NAV tracking + reporting
  - fee distribution claims
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import ClassVar

from helios.types import MarketSnapshot, Position, StrategyManifest, TradeIntent


class StrategyAgent(ABC):
    """Subclass me. See Helios.md §10.

    Class-level configuration (override these on your subclass):
        declared_class: e.g. "momentum_v1"
        asset_universe: ["BTC", "ETH", "SOL", "BNB"]
        max_position_size_usd: hard cap per trade
        fee_rate_bps: 2_000 = 20% performance fee on realized profit
    """

    declared_class: ClassVar[str] = ""
    asset_universe: ClassVar[Sequence[str]] = ()
    max_position_size_usd: ClassVar[int] = 0
    fee_rate_bps: ClassVar[int] = 0

    def __init__(self) -> None:
        if not self.declared_class:
            raise RuntimeError(f"{type(self).__name__}.declared_class must be set on the subclass.")
        self._positions: dict[str, Position] = {}
        self._available_capital_usd: float = 0.0

    # ── To be overridden by operators ────────────────────────
    @abstractmethod
    def on_bar(self, asset: str, snapshot: MarketSnapshot) -> TradeIntent | None:
        """Called for each asset on each bar close. Return a TradeIntent to trade,
        or None to do nothing. Phase 0 abstract; Phase 1 wires the runtime."""
        ...

    # ── Helpers available inside on_bar ──────────────────────
    @property
    def available_capital(self) -> float:
        return self._available_capital_usd

    def position_for(self, asset: str) -> float:
        pos = self._positions.get(asset)
        return pos.quantity if pos else 0.0

    def manifest(
        self, *, operator: str, stake_amount_usd: int, max_capacity_usd: int
    ) -> StrategyManifest:
        return StrategyManifest(
            declared_class=self.declared_class,
            asset_universe=self.asset_universe,
            max_capacity_usd=max_capacity_usd,
            fee_rate_bps=self.fee_rate_bps,
            operator=operator,
            stake_amount_usd=stake_amount_usd,
        )
