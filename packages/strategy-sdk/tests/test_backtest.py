"""Tests for the synthetic-bar backtest engine."""

from __future__ import annotations

from helios import (
    Direction,
    MarketSnapshot,
    StrategyAgent,
    TradeIntent,
    run_backtest,
    synthesize_random_walk,
)


class _BuyOnceHoldStrategy(StrategyAgent):
    """LONG once on the second bar, then hold."""

    declared_class = "momentum_v1"
    asset_universe = ("WETH",)
    max_position_size_usd = 5_000
    fee_rate_bps = 2_000

    def __init__(self) -> None:
        super().__init__()
        self._fired = False

    def on_bar(self, asset: str, snapshot: MarketSnapshot) -> TradeIntent | None:
        if self._fired or len(snapshot.prices) < 2:
            return None
        self._fired = True
        return TradeIntent(
            asset_in="USDC", asset_out=asset, amount_in_usd=5_000, direction=Direction.LONG
        )


class _BuyThenExitStrategy(StrategyAgent):
    """LONG on bar 1, EXIT on bar 5."""

    declared_class = "momentum_v1"
    asset_universe = ("WETH",)
    max_position_size_usd = 1_000
    fee_rate_bps = 2_000

    def on_bar(self, asset: str, snapshot: MarketSnapshot) -> TradeIntent | None:
        n = len(snapshot.prices)
        if n == 2:
            return TradeIntent(
                asset_in="USDC", asset_out=asset, amount_in_usd=1_000, direction=Direction.LONG
            )
        if n == 6 and self.position_for(asset) > 0:
            return TradeIntent(
                asset_in=asset, asset_out="USDC", amount_in_asset=0.0, direction=Direction.EXIT
            )
        return None


class _NeverTradesStrategy(StrategyAgent):
    declared_class = "momentum_v1"
    asset_universe = ("WETH",)
    max_position_size_usd = 1_000
    fee_rate_bps = 2_000

    def on_bar(self, asset: str, snapshot: MarketSnapshot) -> TradeIntent | None:
        del asset, snapshot
        return None


def test_buy_and_hold_records_one_fill_and_tracks_nav() -> None:
    prices = {"WETH": [100.0, 100.0, 110.0, 120.0, 130.0]}
    rep = run_backtest(strategy=_BuyOnceHoldStrategy(), prices=prices, initial_capital=10_000)
    # Exactly one entry fill; no realized P&L because we never close.
    long_fills = [f for f in rep.fills if f.direction == Direction.LONG]
    assert len(long_fills) == 1
    assert rep.realized_pnl == 0.0
    # Final NAV > initial because the held WETH rallied 100 → 130.
    assert rep.final_nav > rep.initial_capital
    assert rep.bars == len(prices["WETH"])
    assert len(rep.nav_series) == rep.bars + 1  # initial + per-bar marks


def test_fee_is_charged_on_entry() -> None:
    prices = {"WETH": [100.0, 100.0, 100.0]}
    rep = run_backtest(
        strategy=_BuyOnceHoldStrategy(),
        prices=prices,
        initial_capital=10_000,
        fee_bps=30,
    )
    fill = next(f for f in rep.fills if f.direction == Direction.LONG)
    assert fill.fee_usd == 5_000 * 30 / 10_000  # 15.0
    # NAV at flat price = initial capital - fee.
    assert rep.final_nav == 10_000 - fill.fee_usd


def test_exit_realizes_pnl_and_closes_position() -> None:
    # Price doubles between entry (bar 1, p=100) and exit (bar 5, p=200).
    prices = {"WETH": [100.0, 100.0, 120.0, 150.0, 180.0, 200.0]}
    rep = run_backtest(
        strategy=_BuyThenExitStrategy(),
        prices=prices,
        initial_capital=10_000,
        fee_bps=0,
    )
    exits = [f for f in rep.fills if f.direction == Direction.EXIT]
    assert len(exits) == 1
    # 1_000 USD bought at 100, sold at 200 → +1_000 realized.
    assert rep.realized_pnl > 900
    assert rep.win_rate == 1.0


def test_no_trades_keeps_nav_flat() -> None:
    prices = {"WETH": [100.0, 101.0, 99.0, 100.0]}
    rep = run_backtest(strategy=_NeverTradesStrategy(), prices=prices, initial_capital=10_000)
    assert rep.fills == []
    assert rep.final_nav == 10_000
    assert rep.total_return == 0.0


def test_synthesize_random_walk_is_deterministic() -> None:
    a = synthesize_random_walk(assets=["WETH", "WBTC"], bars=100, seed=42)
    b = synthesize_random_walk(assets=["WETH", "WBTC"], bars=100, seed=42)
    assert a == b


def test_synthesize_random_walk_seed_changes_output() -> None:
    a = synthesize_random_walk(assets=["WETH"], bars=50, seed=1)
    b = synthesize_random_walk(assets=["WETH"], bars=50, seed=2)
    assert a["WETH"] != b["WETH"]


def test_synthesize_random_walk_shape() -> None:
    out = synthesize_random_walk(assets=["A", "B", "C"], bars=64, seed=7)
    assert set(out.keys()) == {"A", "B", "C"}
    for series in out.values():
        assert len(series) == 64
        assert all(p > 0 for p in series)
