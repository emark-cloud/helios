"""Public types exposed to strategy operators."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from enum import IntEnum

from pydantic import BaseModel, Field


class Direction(IntEnum):
    """Trade direction. Mirrors the on-chain enum in StrategyVault."""

    EXIT = 0
    LONG = 1
    SHORT = 2


class TradeIntent(BaseModel):
    """A strategy's intent to place a trade. The SDK turns this into calldata + proof."""

    asset_in: str
    asset_out: str
    direction: Direction
    amount_in_usd: float | None = None
    amount_in_asset: float | None = None
    max_slippage_bps: int = 50
    block_window_bars: int = 5

    def model_post_init(self, _ctx: object) -> None:
        if self.amount_in_usd is None and self.amount_in_asset is None:
            raise ValueError("Provide amount_in_usd or amount_in_asset.")


class Position(BaseModel):
    asset: str
    quantity: float
    avg_entry_price: float
    direction: Direction


class MarketSnapshot(BaseModel):
    """Snapshot the SDK passes to `on_bar`. Contains recent prices for one asset."""

    asset: str
    timestamp: datetime
    prices: list[float] = Field(description="Recent close prices, oldest → newest")
    bar_interval_sec: int = 60

    def return_over(self, bars: int) -> float:
        if len(self.prices) < bars + 1:
            return 0.0
        old = self.prices[-(bars + 1)]
        new = self.prices[-1]
        if old == 0:
            return 0.0
        return (new - old) / old


class StrategyManifest(BaseModel):
    """Mirrors the on-chain manifest. The SDK derives this from the StrategyAgent subclass."""

    declared_class: str
    asset_universe: Sequence[str]
    max_capacity_usd: int
    fee_rate_bps: int
    operator: str
    stake_amount_usd: int
