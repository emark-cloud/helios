"""Day-by-day allocator backtest.

Inputs:
- `BaseAllocator` subclass instance.
- A list of `StrategyNavSeries` — one per strategy under consideration.
  Each carries the strategy's static parameters (fee rate, capacity,
  declared class) plus a daily NAV trace covering the full backtest
  window.
- A `BacktestConfig` (capital, period, user template, fee threshold).

Per-day loop:
1. Build `StrategyCandidate`s from the strategies' state at day `d`,
   including 30-day trailing realised vol / sharpe lifted from the NAV
   series itself.
2. Call `allocator.rank_strategies(user, candidates)` to get scores.
3. Sort candidates desc by score, call `allocator.allocate(user, ranked,
   capital)`.
4. Apply each allocation's `capital_usd` to the next day's per-strategy
   return. Aggregate to a daily P&L.
5. Crystallise allocator fee on the user's net P&L when NAV crosses
   `hwm * (1 + fee_threshold)`. Mirrors `services/sentinel`'s 5%
   threshold.

The output `BacktestReport` aggregates: final NAV, total return,
annualised Sharpe, max drawdown, allocator fees paid, daily NAV path,
and per-strategy fill counts. Two allocators run on the same input
produce different reports — that's the comparison story.

NAV traces are exogenous to the runner: they are either synthesised
for tests or pulled by `data.fetch_nav_series` from Goldsky. The
runner does not know or care which.
"""

from __future__ import annotations

import itertools
import math
import re
import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field

from helios_allocator.backtest.report import BacktestReport
from helios_allocator.base import BaseAllocator
from helios_allocator.types import MetaStrategy, StrategyCandidate

_PERIOD_RE = re.compile(r"^\s*(\d+)\s*([dwmy])\s*$", re.IGNORECASE)
_PERIOD_DAYS = {"d": 1, "w": 7, "m": 30, "y": 365}

# Default user template — pinned to numbers operators see in the demo
# meta-strategy on `/onboard`. Authors override via `BacktestConfig.user`.
_DEFAULT_USER = MetaStrategy(
    user_address="0x" + "0" * 40,
    allowed_strategy_classes=("momentum_v1", "mean_reversion_v1", "yield_rotation_v1"),
    allowed_assets=("USDC", "WKITE", "WETH"),
    allowed_chains=(2368,),
    max_capital_usd=50_000,
    max_per_strategy_bps=4_000,
    max_strategies_count=5,
    drawdown_threshold_bps=2_000,
    max_fee_rate_bps=2_500,
    rebalance_cadence_sec=86_400,
    valid_until=2**63 - 1,
)


@dataclass(frozen=True, slots=True)
class StrategyNavSeries:
    """A strategy's static metadata plus its daily NAV trace.

    `daily_navs[i]` is the strategy's NAV at the start of day `i`. The
    trace must be at least `period_days + 1` long so the runner can
    compute a return from day `i` to day `i+1`.
    """

    strategy_id: str
    declared_class: str
    fee_rate_bps: int
    stake_amount_usd: int
    max_capacity_usd: int
    reputation_score: float  # in [0, 1]
    chain_id: int = 2368
    operator: str = "0x" + "0" * 40
    trades_attested: int = 200  # past cold-start by default
    daily_navs: Sequence[float] = field(default_factory=tuple)

    def returns(self) -> list[float]:
        """Daily returns r_t = navs[t+1] / navs[t] - 1."""
        out: list[float] = []
        for prev, nxt in itertools.pairwise(self.daily_navs):
            if prev <= 0:
                out.append(0.0)
                continue
            out.append((nxt - prev) / prev)
        return out


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    """Tuneable parameters for a single backtest run."""

    capital: int = 50_000
    period: str = "90d"
    user: MetaStrategy = field(default_factory=lambda: _DEFAULT_USER)
    fee_threshold_bps: int = 500  # 5% HWM cross
    annual_trading_days: int = 252


def parse_period(period: str) -> int:
    """`"90d"` → 90, `"3m"` → 90, `"1y"` → 365. Raises on bad input."""
    m = _PERIOD_RE.match(period)
    if not m:
        raise ValueError(f"period {period!r} not parseable; expected forms like '30d', '3m', '1y'.")
    n = int(m.group(1))
    unit = m.group(2).lower()
    return n * _PERIOD_DAYS[unit]


def run_backtest(
    allocator: BaseAllocator,
    strategies: Sequence[StrategyNavSeries],
    config: BacktestConfig | None = None,
) -> BacktestReport:
    """Replay `strategies` day-by-day against `allocator`'s decisions."""
    cfg = config or BacktestConfig()
    period_days = parse_period(cfg.period)
    if not strategies:
        raise ValueError("backtest requires at least one strategy in the universe.")
    for s in strategies:
        if len(s.daily_navs) < period_days + 1:
            raise ValueError(
                f"strategy {s.strategy_id} has {len(s.daily_navs)} NAV samples; "
                f"need at least {period_days + 1} for a {cfg.period} backtest."
            )

    returns_by_strategy = {s.strategy_id: s.returns() for s in strategies}

    user_capital = float(cfg.capital)
    user_hwm = user_capital
    fee_threshold = 1.0 + (cfg.fee_threshold_bps / 10_000.0)
    fees_paid = 0.0
    daily_nav: list[float] = [user_capital]
    daily_returns: list[float] = []
    decisions: list[dict[str, float]] = []
    fills_by_strategy: dict[str, int] = {s.strategy_id: 0 for s in strategies}

    for day in range(period_days):
        candidates = [_candidate_at(s, day, cfg.annual_trading_days) for s in strategies]
        scores = allocator.rank_strategies(cfg.user, candidates)
        if len(scores) != len(candidates):
            raise RuntimeError(
                "rank_strategies returned wrong number of scores: "
                f"{len(scores)} vs {len(candidates)}."
            )
        ranked = [c for _, c in sorted(zip(scores, candidates, strict=True), key=lambda p: -p[0])]
        targets = allocator.allocate(cfg.user, ranked, int(user_capital))

        # Apply per-strategy day-d returns to the dollar allocations.
        gross_pnl = 0.0
        for t in targets:
            r = returns_by_strategy[t.strategy_id][day]
            gross_pnl += t.capital_usd * r
            if t.capital_usd > 0:
                fills_by_strategy[t.strategy_id] += 1

        new_nav = user_capital + gross_pnl
        # Allocator fee on HWM cross — mirrors fees.crystallise_if_above_hwm.
        if new_nav > user_hwm * fee_threshold:
            profit_above_hwm = new_nav - user_hwm
            fee = profit_above_hwm * (allocator.fee_rate_bps / 10_000.0)
            fee = max(0.0, fee)
            new_nav -= fee
            fees_paid += fee
            user_hwm = new_nav

        ret = (new_nav - user_capital) / user_capital if user_capital > 0 else 0.0
        daily_returns.append(ret)
        decisions.append(
            {
                "day": float(day),
                "nav_pre_fee": user_capital + gross_pnl,
                "nav": new_nav,
                "n_targets": float(len(targets)),
            }
        )
        user_capital = new_nav
        daily_nav.append(user_capital)

    return BacktestReport(
        allocator_name=allocator.name or type(allocator).__name__,
        capital=cfg.capital,
        period=cfg.period,
        period_days=period_days,
        final_nav=user_capital,
        total_return=(user_capital - cfg.capital) / cfg.capital if cfg.capital else 0.0,
        sharpe=_annualised_sharpe(daily_returns, cfg.annual_trading_days),
        max_drawdown=_max_drawdown(daily_nav),
        allocator_fees_paid=fees_paid,
        daily_nav=daily_nav,
        decisions=decisions,
        fills_by_strategy=dict(fills_by_strategy),
    )


def _candidate_at(
    s: StrategyNavSeries,
    day: int,
    annual_days: int,
) -> StrategyCandidate:
    """Build a candidate snapshot using everything up to (and including)
    `day`. The trailing 30-day realised vol / Sharpe are computed from
    the same NAV trace the runner replays — this matches what the live
    allocator sees through Goldsky on day `day`."""
    window_start = max(0, day - 30)
    window = s.daily_navs[window_start : day + 1]
    rets: list[float] = []
    for prev, nxt in itertools.pairwise(window):
        if prev > 0:
            rets.append((nxt - prev) / prev)
    sd = _stdev(rets) if len(rets) > 1 else 0.0
    realized_vol = sd * math.sqrt(annual_days)
    mean_r = statistics.fmean(rets) if rets else 0.0
    sharpe = (mean_r / sd * math.sqrt(annual_days)) if sd > 0 else 0.0
    max_dd_window = _max_drawdown(list(window)) if len(window) > 1 else 0.0
    return StrategyCandidate(
        strategy_id=s.strategy_id,
        declared_class=s.declared_class,
        chain_id=s.chain_id,
        operator=s.operator,
        fee_rate_bps=s.fee_rate_bps,
        stake_amount_usd=s.stake_amount_usd,
        max_capacity_usd=s.max_capacity_usd,
        current_allocations_usd=0,
        reputation_score=s.reputation_score,
        realized_volatility_30d=realized_vol,
        sharpe_30d=sharpe,
        max_drawdown_30d_bps=int(max_dd_window * 10_000),
        trades_attested=s.trades_attested,
    )


def _stdev(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    return statistics.pstdev(xs)


def _annualised_sharpe(daily_returns: Sequence[float], annual_days: int) -> float:
    if len(daily_returns) < 2:
        return 0.0
    sd = _stdev(daily_returns)
    if sd == 0:
        return 0.0
    return statistics.fmean(daily_returns) / sd * math.sqrt(annual_days)


def _max_drawdown(navs: Sequence[float]) -> float:
    """Largest peak-to-trough drawdown as a positive fraction (0.2 = 20%)."""
    peak = -math.inf
    worst = 0.0
    for v in navs:
        peak = max(peak, v)
        if peak > 0:
            dd = (peak - v) / peak
            worst = max(worst, dd)
    return worst


__all__ = [
    "BacktestConfig",
    "StrategyNavSeries",
    "parse_period",
    "run_backtest",
]
