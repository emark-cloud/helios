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
from helios.runtime import (
    ChainSurface,
    ChainTarget,
    DeploymentNotFoundError,
    VenueMode,
    load_chain_surface,
)
from helios.sizing import nav_target_notional
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
    "ChainSurface",
    "ChainTarget",
    "DeploymentNotFoundError",
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
    "VenueMode",
    "YieldBacktestReport",
    "YieldTick",
    "load_chain_surface",
    "max_drawdown",
    "nav_target_notional",
    "run_backtest",
    "run_yield_backtest",
    "sharpe_ratio",
    "synthesize_random_walk",
]

__version__ = "0.1.0"
