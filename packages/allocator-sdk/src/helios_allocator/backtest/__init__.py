"""Allocator backtest harness (WS1.C).

Replays a list of `StrategyNavSeries` day-by-day against an allocator's
`rank_strategies` + `allocate` decisions, measuring user net P&L,
drawdown, and allocator-fee take. The runner is fully synchronous and
in-memory; the only async surface is `data.fetch_nav_series` which
pulls historical NAVSnapshot rows from Goldsky.

Authors compare two allocators by running the same input through both
and diffing the reports — see `tests/test_backtest_runner.py`.
"""

from helios_allocator.backtest.data import (
    GoldskyHistoricalClient,
    fetch_nav_series,
)
from helios_allocator.backtest.report import (
    BacktestReport,
    render_json,
    render_markdown,
)
from helios_allocator.backtest.runner import (
    BacktestConfig,
    StrategyNavSeries,
    parse_period,
    run_backtest,
)

__all__ = [
    "BacktestConfig",
    "BacktestReport",
    "GoldskyHistoricalClient",
    "StrategyNavSeries",
    "fetch_nav_series",
    "parse_period",
    "render_json",
    "render_markdown",
    "run_backtest",
]
