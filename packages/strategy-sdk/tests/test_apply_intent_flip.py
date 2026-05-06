"""Tests for position flipping in `_apply_intent` (WS4 PR 2/3).

When a directional `TradeIntent` arrives on top of an existing
opposite-side position, the engine must close the prior leg first
(realising P&L) before opening the new side. Without this, the avg-
entry of the resulting net position is a meaningless mix of two
opposing legs and the closing leg's gain/loss never lands in
`BacktestReport.realized_pnl`.

Scenarios covered:
  * SHORT held → LONG intent arrives → engine emits an EXIT fill on
    the short, then a LONG entry fill. Realized P&L of the short
    close lands on `BacktestReport.realized_pnl`. The strategy ends
    long-only.
  * LONG held → SHORT intent arrives → mirror.
  * The flip path realises a positive P&L when the price moves the
    right way (short profits when price drops, then flips long).
"""

from __future__ import annotations

import pytest
from helios import (
    Direction,
    MarketSnapshot,
    StrategyAgent,
    TradeIntent,
    run_backtest,
)


class _ShortThenLongFlipStrategy(StrategyAgent):
    """First on_bar call: SHORT entry. Fifth call: LONG entry (flip).
    Subsequent calls: hold.

    Used to verify that the engine closes the short and opens the long
    in one `_apply_intent` call, with the short's realised P&L landing
    on the report.
    """

    declared_class = "test_class_v1"
    asset_universe = ("BTC",)
    max_position_size_usd = 1_000
    fee_rate_bps = 0  # zero fees so we can assert exact P&L

    def __init__(self) -> None:
        super().__init__()
        self._calls = 0

    def on_bar(self, asset: str, snapshot: MarketSnapshot) -> TradeIntent | None:
        del asset, snapshot
        self._calls += 1
        if self._calls == 1:
            return TradeIntent(
                asset_in="BTC",
                asset_out="USDC",
                amount_in_usd=1_000,
                direction=Direction.SHORT,
                max_slippage_bps=30,
            )
        if self._calls == 5:
            return TradeIntent(
                asset_in="USDC",
                asset_out="BTC",
                amount_in_usd=1_000,
                direction=Direction.LONG,
                max_slippage_bps=30,
            )
        return None


class _LongThenShortFlipStrategy(StrategyAgent):
    """First call LONG, fifth call SHORT (flip), then hold."""

    declared_class = "test_class_v1"
    asset_universe = ("BTC",)
    max_position_size_usd = 1_000
    fee_rate_bps = 0

    def __init__(self) -> None:
        super().__init__()
        self._calls = 0

    def on_bar(self, asset: str, snapshot: MarketSnapshot) -> TradeIntent | None:
        del asset, snapshot
        self._calls += 1
        if self._calls == 1:
            return TradeIntent(
                asset_in="USDC",
                asset_out="BTC",
                amount_in_usd=1_000,
                direction=Direction.LONG,
                max_slippage_bps=30,
            )
        if self._calls == 5:
            return TradeIntent(
                asset_in="BTC",
                asset_out="USDC",
                amount_in_usd=1_000,
                direction=Direction.SHORT,
                max_slippage_bps=30,
            )
        return None


def _flat_then_drop(initial: float, drop_to: float, bars: int = 20) -> dict[str, list[float]]:
    """Bars 0–4: flat at `initial`. Bars 5+: flat at `drop_to`.

    A short opened at bar 0 and flipped to long at bar 5 should realise
    `initial - drop_to` per unit of the short close.
    """
    return {"BTC": [initial] * 5 + [drop_to] * (bars - 5)}


def _flat_then_rise(initial: float, rise_to: float, bars: int = 20) -> dict[str, list[float]]:
    return {"BTC": [initial] * 5 + [rise_to] * (bars - 5)}


# ─── SHORT → LONG flip ─────────────────────────────────────


def test_short_to_long_flip_realises_short_pnl() -> None:
    # Short at $100, price drops to $90 by bar 5, flip to long.
    # Short qty = -1000/100 = -10. Realised on close at 90:
    #   short PnL = (avg_entry - close_price) * |qty| = (100-90)*10 = 100.
    prices = _flat_then_drop(100.0, 90.0, bars=20)
    report = run_backtest(
        strategy=_ShortThenLongFlipStrategy(),
        prices=prices,
        initial_capital=10_000.0,
        bar_interval_sec=60,
        fee_bps=0,
    )
    # Three fills total: SHORT entry, EXIT (the flip-close), LONG entry.
    fills_by_dir = [f.direction for f in report.fills]
    assert fills_by_dir == [Direction.SHORT, Direction.EXIT, Direction.LONG]
    assert pytest.approx(report.realized_pnl, abs=1e-6) == 100.0
    # Final position is LONG; quantity = 1000/90 ≈ 11.111.
    assert report.fills[-1].direction == Direction.LONG
    assert pytest.approx(report.fills[-1].quantity, rel=1e-6) == 1_000 / 90


def test_short_to_long_flip_records_a_win() -> None:
    """A profitable flip-close should bump the win counter, not be lost
    in the noise."""
    prices = _flat_then_drop(100.0, 90.0, bars=20)
    report = run_backtest(
        strategy=_ShortThenLongFlipStrategy(),
        prices=prices,
        initial_capital=10_000.0,
        bar_interval_sec=60,
        fee_bps=0,
    )
    # The short close is the only realised trade in this test (the
    # subsequent LONG entry has no exit). One win, zero losses.
    assert report.win_rate == 1.0


# ─── LONG → SHORT flip ─────────────────────────────────────


def test_long_to_short_flip_realises_long_pnl() -> None:
    # Long at $100, price rises to $110 by bar 5, flip to short.
    # Long qty = 1000/100 = 10. Realised on close at 110:
    #   long PnL = close_price * |qty| - cost = 110*10 - 100*10 = 100.
    prices = _flat_then_rise(100.0, 110.0, bars=20)
    report = run_backtest(
        strategy=_LongThenShortFlipStrategy(),
        prices=prices,
        initial_capital=10_000.0,
        bar_interval_sec=60,
        fee_bps=0,
    )
    fills_by_dir = [f.direction for f in report.fills]
    assert fills_by_dir == [Direction.LONG, Direction.EXIT, Direction.SHORT]
    assert pytest.approx(report.realized_pnl, abs=1e-6) == 100.0
    assert report.fills[-1].direction == Direction.SHORT


def test_long_to_short_flip_loses_when_price_drops() -> None:
    # Long at $100, price drops to $90 by bar 5, flip to short.
    # Long PnL = 90*10 - 100*10 = -100.
    prices = _flat_then_drop(100.0, 90.0, bars=20)
    report = run_backtest(
        strategy=_LongThenShortFlipStrategy(),
        prices=prices,
        initial_capital=10_000.0,
        bar_interval_sec=60,
        fee_bps=0,
    )
    assert pytest.approx(report.realized_pnl, abs=1e-6) == -100.0
    assert report.win_rate == 0.0


# ─── same-direction stack does NOT flip ────────────────────


class _LongTwiceStrategy(StrategyAgent):
    """First call: LONG. Fifth call: LONG again. No flip — should
    accumulate at VWAP without realising any P&L."""

    declared_class = "test_class_v1"
    asset_universe = ("BTC",)
    max_position_size_usd = 1_000
    fee_rate_bps = 0

    def __init__(self) -> None:
        super().__init__()
        self._calls = 0

    def on_bar(self, asset: str, snapshot: MarketSnapshot) -> TradeIntent | None:
        del asset, snapshot
        self._calls += 1
        if self._calls in (1, 5):
            return TradeIntent(
                asset_in="USDC",
                asset_out="BTC",
                amount_in_usd=500,
                direction=Direction.LONG,
                max_slippage_bps=30,
            )
        return None


def test_same_direction_stack_does_not_realise_pnl() -> None:
    """Sanity: the flip path must not fire when the new intent matches
    the held side. Two LONG entries at different prices accumulate at
    VWAP and produce zero realised P&L (realised only happens on
    EXIT or flip).
    """
    prices = _flat_then_rise(100.0, 110.0, bars=20)
    report = run_backtest(
        strategy=_LongTwiceStrategy(),
        prices=prices,
        initial_capital=10_000.0,
        bar_interval_sec=60,
        fee_bps=0,
    )
    fills_by_dir = [f.direction for f in report.fills]
    assert fills_by_dir == [Direction.LONG, Direction.LONG]  # no EXIT in between
    assert report.realized_pnl == 0.0
