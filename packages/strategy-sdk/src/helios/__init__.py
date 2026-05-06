"""Helios strategy SDK.

Public surface for shipping a strategy on the Helios marketplace.
See Helios.md §10 for the full contract.
"""

from helios.agent import StrategyAgent
from helios.backtest import (
    BacktestReport,
    Rotation,
    TradeFill,
    YieldBacktestReport,
    run_backtest,
    run_yield_backtest,
    synthesize_random_walk,
)
from helios.nav import NAVTracker, max_drawdown, sharpe_ratio
from helios.types import (
    Direction,
    MarketSnapshot,
    Position,
    RotationIntent,
    StrategyManifest,
    TradeIntent,
    YieldTick,
)

__all__ = [
    "BacktestReport",
    "Direction",
    "MarketSnapshot",
    "NAVTracker",
    "Position",
    "Rotation",
    "RotationIntent",
    "StrategyAgent",
    "StrategyManifest",
    "TradeFill",
    "TradeIntent",
    "YieldBacktestReport",
    "YieldTick",
    "max_drawdown",
    "run_backtest",
    "run_yield_backtest",
    "sharpe_ratio",
    "synthesize_random_walk",
]

__version__ = "0.1.0"
