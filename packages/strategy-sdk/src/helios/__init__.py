"""Helios strategy SDK.

Public surface for shipping a strategy on the Helios marketplace.
See Helios.md §10 for the full contract.
"""

from helios.agent import StrategyAgent
from helios.backtest import (
    BacktestReport,
    TradeFill,
    run_backtest,
    synthesize_random_walk,
)
from helios.nav import NAVTracker, max_drawdown, sharpe_ratio
from helios.types import (
    Direction,
    MarketSnapshot,
    Position,
    StrategyManifest,
    TradeIntent,
)

__all__ = [
    "BacktestReport",
    "Direction",
    "MarketSnapshot",
    "NAVTracker",
    "Position",
    "StrategyAgent",
    "StrategyManifest",
    "TradeFill",
    "TradeIntent",
    "max_drawdown",
    "run_backtest",
    "sharpe_ratio",
    "synthesize_random_walk",
]

__version__ = "0.1.0"
