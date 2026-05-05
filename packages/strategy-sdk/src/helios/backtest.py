"""Synthetic-bar backtest engine.

Drives a `StrategyAgent` against a multi-asset price series and
returns a `BacktestReport` with NAV history, trades, Sharpe, max
drawdown, and win rate.

Used by `helios backtest` (real historical replay) and `helios
simulate` (mocked-up market loop). Pure Python, no I/O — caller
supplies the price series."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from helios.agent import StrategyAgent
from helios.nav import BARS_PER_YEAR_1M, NAVTracker
from helios.types import Direction, MarketSnapshot, TradeIntent

# Bars of look-back included in each MarketSnapshot.prices window.
DEFAULT_LOOKBACK_BARS = 32

# Per-trade fee in bps applied symmetrically on entry + exit. Mirrors a
# 30 bps swap cost on the Phase 1 mock router; operators with a
# different exchange model can pass `fee_bps` to override.
DEFAULT_FEE_BPS = 30


@dataclass
class TradeFill:
    """One executed leg of a trade in the backtest."""

    bar: int
    timestamp: datetime
    asset: str
    direction: Direction
    price: float
    quantity: float
    notional_usd: float
    fee_usd: float


@dataclass
class BacktestReport:
    """Result of one backtest run."""

    initial_capital: float
    final_nav: float
    bars: int
    fills: list[TradeFill] = field(default_factory=list)
    nav_series: list[float] = field(default_factory=list)
    total_return: float = 0.0
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    realized_pnl: float = 0.0

    def summary(self) -> str:
        """Plain-text one-screen summary used by `helios backtest`."""
        return (
            f"Bars:           {self.bars}\n"
            f"Initial:        ${self.initial_capital:,.2f}\n"
            f"Final NAV:      ${self.final_nav:,.2f}\n"
            f"Total return:   {self.total_return * 100:+.2f}%\n"
            f"Sharpe (ann.):  {self.sharpe:.2f}\n"
            f"Max drawdown:   {self.max_drawdown * 100:.2f}%\n"
            f"Realized P&L:   ${self.realized_pnl:+,.2f}\n"
            f"Trades:         {len(self.fills)}\n"
            f"Win rate:       {self.win_rate * 100:.1f}%\n"
        )


def run_backtest(
    *,
    strategy: StrategyAgent,
    prices: Mapping[str, Sequence[float]],
    initial_capital: float = 10_000.0,
    bar_interval_sec: int = 60,
    lookback_bars: int = DEFAULT_LOOKBACK_BARS,
    fee_bps: int = DEFAULT_FEE_BPS,
    start_time: datetime | None = None,
) -> BacktestReport:
    """Run `strategy` against the supplied multi-asset price series.

    Parameters
    ----------
    strategy:
        A `StrategyAgent` subclass instance.
    prices:
        Mapping `asset_symbol -> list[close_price]`. All series must be
        the same length. The base asset (typically `"USDC"`) is always
        worth $1.
    initial_capital:
        Starting NAV in USD.
    bar_interval_sec:
        Bar cadence; only used to label fills and to choose the Sharpe
        annualisation factor.
    lookback_bars:
        Window size handed to `MarketSnapshot.prices`. The strategy
        only sees `prices[bar - lookback : bar + 1]`. Fewer bars than
        the lookback at the start are tolerated; the snapshot just
        contains whatever's available.
    fee_bps:
        Round-trip fee charged at each fill, in basis points.
    start_time:
        Wall-clock for `MarketSnapshot.timestamp`. Defaults to now (UTC).
    """
    if not prices:
        raise ValueError("prices must not be empty")
    series_lens = {len(v) for v in prices.values()}
    if len(series_lens) != 1:
        raise ValueError("all price series must have the same length")
    n_bars = series_lens.pop()
    if n_bars < 2:
        raise ValueError("need at least two bars to backtest")

    bars_per_year = max(1, (365 * 24 * 60 * 60) // max(1, bar_interval_sec))
    bars_per_year = bars_per_year if bars_per_year > 0 else BARS_PER_YEAR_1M
    nav = NAVTracker(initial_nav=initial_capital, bars_per_year=bars_per_year)
    cash = float(initial_capital)
    holdings: dict[str, float] = {}
    fills: list[TradeFill] = []
    start_time = start_time or datetime.now(UTC)

    strategy._set_capital(cash)
    strategy._set_nav(cash)
    counters = _Counters()

    for bar in range(n_bars):
        ts = start_time + timedelta(seconds=bar * bar_interval_sec)
        # PR4: refresh mark-to-market NAV before any asset's `on_bar` runs
        # so sizing helpers (`self.nav * fraction`) scale to the strategy's
        # full footprint, not just leftover cash. Use the prior bar's
        # close (= prices[a][bar-1] for bar > 0) since this bar's print
        # has not yet executed.
        if bar > 0:
            mtm_pre = cash + sum(
                qty * float(prices[a][bar - 1])
                for a, qty in holdings.items()
                if a in prices and qty != 0
            )
            strategy._set_nav(mtm_pre)
        for asset in strategy.asset_universe:
            if asset not in prices:
                continue
            window_lo = max(0, bar - lookback_bars + 1)
            window = list(prices[asset][window_lo : bar + 1])
            if len(window) < 2:
                continue
            cash = _step_asset(
                strategy=strategy,
                bar=bar,
                ts=ts,
                asset=asset,
                window=window,
                bar_interval_sec=bar_interval_sec,
                cash=cash,
                holdings=holdings,
                fills=fills,
                fee_bps=fee_bps,
                counters=counters,
            )

        mark_to_market = cash + sum(
            qty * float(prices[a][bar]) for a, qty in holdings.items() if a in prices and qty != 0
        )
        nav.record(mark_to_market)

    realized_pnl = counters.realized_pnl
    realized_wins = counters.wins
    realized_losses = counters.losses

    closed_trades = realized_wins + realized_losses
    win_rate = (realized_wins / closed_trades) if closed_trades else 0.0
    return BacktestReport(
        initial_capital=initial_capital,
        final_nav=nav.current,
        bars=n_bars,
        fills=fills,
        nav_series=nav.navs,
        total_return=nav.total_return,
        sharpe=nav.sharpe(),
        max_drawdown=nav.max_drawdown,
        win_rate=win_rate,
        realized_pnl=realized_pnl,
    )


@dataclass
class _Counters:
    realized_pnl: float = 0.0
    wins: int = 0
    losses: int = 0


def _step_asset(
    *,
    strategy: StrategyAgent,
    bar: int,
    ts: datetime,
    asset: str,
    window: list[float],
    bar_interval_sec: int,
    cash: float,
    holdings: dict[str, float],
    fills: list[TradeFill],
    fee_bps: int,
    counters: _Counters,
) -> float:
    """One asset's update for one bar. Returns updated cash balance."""
    snapshot = MarketSnapshot(
        asset=asset,
        timestamp=ts,
        prices=window,
        bar_interval_sec=bar_interval_sec,
    )

    position_obj = strategy.position_object(asset)
    if position_obj is not None and strategy.should_exit(asset, snapshot, position_obj):
        fill, cash, realized = _close_position(
            bar=bar,
            ts=ts,
            asset=asset,
            price=window[-1],
            qty=position_obj.quantity,
            avg_entry=position_obj.avg_entry_price,
            direction=position_obj.direction,
            fee_bps=fee_bps,
            cash=cash,
        )
        fills.append(fill)
        strategy._set_position(asset, 0.0, 0.0, Direction.EXIT)
        holdings.pop(asset, None)
        counters.realized_pnl += realized
        if realized >= 0:
            counters.wins += 1
        else:
            counters.losses += 1
        strategy._set_capital(cash)

    intent = strategy.on_bar(asset, snapshot)
    if intent is None:
        return cash
    cash, realized = _apply_intent(
        strategy=strategy,
        bar=bar,
        ts=ts,
        asset=asset,
        intent=intent,
        price=window[-1],
        cash=cash,
        holdings=holdings,
        fills=fills,
        fee_bps=fee_bps,
    )
    counters.realized_pnl += realized
    if realized > 0:
        counters.wins += 1
    elif realized < 0:
        counters.losses += 1
    strategy._set_capital(cash)
    return cash


def _apply_intent(
    *,
    strategy: StrategyAgent,
    bar: int,
    ts: datetime,
    asset: str,
    intent: TradeIntent,
    price: float,
    cash: float,
    holdings: dict[str, float],
    fills: list[TradeFill],
    fee_bps: int,
) -> tuple[float, float]:
    """Execute one TradeIntent against the synthetic order book.

    Returns the new cash balance and any realized P&L produced by this
    fill (non-zero on EXIT or signal-flipping LONG/SHORT)."""
    if price <= 0:
        return cash, 0.0
    direction = Direction(int(intent.direction))
    realized = 0.0

    if direction == Direction.EXIT:
        held = holdings.get(asset, 0.0)
        if held == 0:
            return cash, 0.0
        position_obj = strategy.position_object(asset)
        avg_entry = position_obj.avg_entry_price if position_obj else price
        held_dir = position_obj.direction if position_obj else Direction.LONG
        fill, cash, realized = _close_position(
            bar=bar,
            ts=ts,
            asset=asset,
            price=price,
            qty=held,
            avg_entry=avg_entry,
            direction=held_dir,
            fee_bps=fee_bps,
            cash=cash,
        )
        fills.append(fill)
        holdings.pop(asset, None)
        strategy._set_position(asset, 0.0, 0.0, Direction.EXIT)
        return cash, realized

    notional = strategy.size_trade(intent, available_capital=cash)
    if notional <= 0:
        return cash, 0.0
    fee = notional * fee_bps / 10_000
    if notional + fee > cash:
        # Down-size to fit available capital after fees.
        notional = max(0.0, cash * 10_000 / (10_000 + fee_bps))
        fee = notional * fee_bps / 10_000
        if notional <= 0:
            return cash, 0.0

    qty = notional / price if direction == Direction.LONG else -notional / price
    if direction == Direction.LONG:
        cash -= notional + fee
        # Accumulate at volume-weighted average price (LONG only — Phase
        # 1 reference momentum strategy never flips short → long without
        # an explicit EXIT).
        prev_qty = holdings.get(asset, 0.0)
        prev_pos = strategy.position_object(asset)
        prev_avg = prev_pos.avg_entry_price if prev_pos is not None else 0.0
        new_qty = prev_qty + qty
        new_avg = ((prev_avg * prev_qty) + (price * qty)) / new_qty if new_qty else price
        holdings[asset] = new_qty
        strategy._set_position(asset, new_qty, new_avg, Direction.LONG)
    else:
        # SHORT entry: credit cash with the short proceeds (less fee).
        # Mark-to-market on the per-bar loop subtracts `holdings[asset] *
        # price` from NAV — the credit here keeps NAV cash-neutral at
        # entry, so NAV starts at (initial − fee) and tracks
        # (avg_entry − current_price) × |qty| as price moves. The
        # `notional + fee > cash` guard above stays as a synthetic
        # margin requirement (you can only short up to free cash).
        cash += notional - fee
        prev_qty = holdings.get(asset, 0.0)
        new_qty = prev_qty + qty
        holdings[asset] = new_qty
        # PR4: store the SIGNED quantity (negative for shorts) so callers
        # of `StrategyAgent.position_for(asset) < 0` actually see the
        # short. Earlier code stored `abs(new_qty)` and silently broke
        # any consumer that branched on direction via the sign.
        strategy._set_position(asset, new_qty, price, Direction.SHORT)

    fills.append(
        TradeFill(
            bar=bar,
            timestamp=ts,
            asset=asset,
            direction=direction,
            price=price,
            quantity=qty,
            notional_usd=notional,
            fee_usd=fee,
        )
    )
    return cash, realized


def _close_position(
    *,
    bar: int,
    ts: datetime,
    asset: str,
    price: float,
    qty: float,
    avg_entry: float,
    direction: Direction,
    fee_bps: int,
    cash: float,
) -> tuple[TradeFill, float, float]:
    """Realize a position back to cash. Returns (fill, new_cash, pnl)."""
    notional = abs(qty) * price
    fee = notional * fee_bps / 10_000
    if direction == Direction.LONG:
        proceeds = notional - fee
        cost = abs(qty) * avg_entry
        realized = proceeds - cost
        cash += proceeds
    else:
        # Short close: pay buyback at current price. The original short
        # proceeds were already credited to cash on entry (see
        # `_apply_intent`'s SHORT branch), so we only debit the cost
        # here. Realized P&L is the net (entry credit − buyback cost).
        cost = notional + fee
        proceeds_at_entry = abs(qty) * avg_entry
        realized = proceeds_at_entry - cost
        cash -= cost
    fill = TradeFill(
        bar=bar,
        timestamp=ts,
        asset=asset,
        direction=Direction.EXIT,
        price=price,
        quantity=qty,
        notional_usd=notional,
        fee_usd=fee,
    )
    return fill, cash, realized


def synthesize_random_walk(
    *,
    assets: Sequence[str],
    bars: int,
    start_price: float = 100.0,
    drift_per_bar: float = 0.0,
    vol_per_bar: float = 0.005,
    seed: int = 0,
) -> dict[str, list[float]]:
    """Generate a deterministic geometric random walk for `helios simulate`.

    Pure-Python LCG so backtests reproduce bit-for-bit in CI without
    pulling numpy as an SDK dependency."""
    state = seed if seed != 0 else 0xDEADBEEF
    out: dict[str, list[float]] = {}
    for i, asset in enumerate(assets):
        prices = [start_price * (1.0 + 0.01 * i)]
        local = state ^ (0x9E3779B1 * (i + 1) & 0xFFFFFFFF)
        for _ in range(bars - 1):
            local = (1664525 * local + 1013904223) & 0xFFFFFFFF
            u = (local & 0xFFFFFF) / 0xFFFFFF  # uniform in [0, 1)
            # Box-Muller-lite using two LCG draws
            local = (1664525 * local + 1013904223) & 0xFFFFFFFF
            v = ((local & 0xFFFFFF) / 0xFFFFFF) or 1e-9
            z = math.sqrt(-2.0 * math.log(v)) * math.cos(2.0 * math.pi * u)
            prices.append(prices[-1] * math.exp(drift_per_bar + vol_per_bar * z))
        out[asset] = prices
    return out
