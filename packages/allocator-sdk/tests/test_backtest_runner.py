"""Tests for `helios_allocator.backtest.run_backtest` (WS1.C).

Three deterministic strategies, two allocators, one assertion:
the allocators produce different P&L on identical input. That's the
backtest harness's reason to exist — it lets an author compare
ranking changes pre-deploy.

The synthetic NAV traces are constructed so:
  - `strat_alpha` drifts up steadily (good momentum candidate),
  - `strat_beta` drifts down (penalised by reputation prior),
  - `strat_gamma` oscillates around a flat mean (fee-sensitive,
    favoured by an allocator that weights cost-of-trade).

A reputation-weighted allocator concentrates on `strat_alpha`; a
fee-weighted allocator that derates expensive strategies prefers
`strat_gamma`. The runner replays both and the gross P&Ls diverge.
"""

from __future__ import annotations

import json
import math

import pytest
from helios_allocator.backtest import (
    BacktestConfig,
    StrategyNavSeries,
    parse_period,
    render_json,
    render_markdown,
    run_backtest,
)
from helios_allocator.base import BaseAllocator
from helios_allocator.types import AllocationTarget, MetaStrategy, StrategyCandidate

# ─── allocators under test ─────────────────────────────────


class ReputationOnlyAllocator(BaseAllocator):
    """Heavily concentrates on the highest-reputation candidate."""

    name = "RepOnly"
    fee_rate_bps = 500
    supported_classes = ("momentum_v1", "mean_reversion_v1", "yield_rotation_v1")

    def rank_strategies(
        self,
        user: MetaStrategy,
        candidates: list[StrategyCandidate],
    ) -> list[float]:
        # Cube the reputation so the top one absorbs almost all weight
        # under score-weighted allocation.
        return [c.reputation_score**3 for c in candidates]

    def allocate(
        self,
        user: MetaStrategy,
        ranked: list[StrategyCandidate],
        capital: int,
    ) -> list[AllocationTarget]:
        scores = self.rank_strategies(user, ranked)
        return self.score_weighted_allocation(user, ranked, capital, scores=scores)


class FeeAverseAllocator(BaseAllocator):
    """Penalises expensive strategies aggressively."""

    name = "FeeAverse"
    fee_rate_bps = 500
    supported_classes = ("momentum_v1", "mean_reversion_v1", "yield_rotation_v1")

    def rank_strategies(
        self,
        user: MetaStrategy,
        candidates: list[StrategyCandidate],
    ) -> list[float]:
        scores: list[float] = []
        for c in candidates:
            base = c.reputation_score
            fee_pen = 1.0 / (1.0 + (c.fee_rate_bps / 1_000.0))
            scores.append(base * fee_pen)
        return scores

    def allocate(
        self,
        user: MetaStrategy,
        ranked: list[StrategyCandidate],
        capital: int,
    ) -> list[AllocationTarget]:
        scores = self.rank_strategies(user, ranked)
        return self.score_weighted_allocation(user, ranked, capital, scores=scores)


# ─── synthetic NAV traces ──────────────────────────────────

_PERIOD_DAYS = 60


def _drifting(start: float, daily_drift: float, days: int) -> list[float]:
    return [start * ((1.0 + daily_drift) ** d) for d in range(days + 1)]


def _oscillating(mid: float, amplitude: float, period: int, days: int) -> list[float]:
    return [mid + amplitude * math.sin(2 * math.pi * d / period) for d in range(days + 1)]


def _universe() -> list[StrategyNavSeries]:
    return [
        StrategyNavSeries(
            strategy_id="0xalpha",
            declared_class="momentum_v1",
            fee_rate_bps=2_000,
            stake_amount_usd=10_000,
            max_capacity_usd=200_000,
            reputation_score=0.9,
            daily_navs=tuple(_drifting(100.0, 0.003, _PERIOD_DAYS)),
        ),
        StrategyNavSeries(
            strategy_id="0xbeta",
            declared_class="mean_reversion_v1",
            fee_rate_bps=1_500,
            stake_amount_usd=8_000,
            max_capacity_usd=150_000,
            reputation_score=0.4,
            daily_navs=tuple(_drifting(100.0, -0.001, _PERIOD_DAYS)),
        ),
        StrategyNavSeries(
            strategy_id="0xgamma",
            declared_class="yield_rotation_v1",
            fee_rate_bps=300,
            stake_amount_usd=5_000,
            max_capacity_usd=100_000,
            reputation_score=0.55,
            daily_navs=tuple(_oscillating(100.0, 1.5, 14, _PERIOD_DAYS)),
        ),
    ]


# ─── tests ─────────────────────────────────────────────────


def test_parse_period() -> None:
    assert parse_period("90d") == 90
    assert parse_period("3m") == 90
    assert parse_period("1y") == 365
    assert parse_period(" 60D ") == 60
    with pytest.raises(ValueError):
        parse_period("forever")


def test_run_backtest_produces_expected_shape() -> None:
    cfg = BacktestConfig(capital=50_000, period=f"{_PERIOD_DAYS}d")
    report = run_backtest(ReputationOnlyAllocator(), _universe(), cfg)
    assert report.allocator_name == "RepOnly"
    assert report.period_days == _PERIOD_DAYS
    # daily_nav has period_days + 1 entries (open + each close).
    assert len(report.daily_nav) == _PERIOD_DAYS + 1
    assert len(report.decisions) == _PERIOD_DAYS
    # Capital starts at 50k, never drops below the worst-allowed drawdown.
    assert report.daily_nav[0] == pytest.approx(50_000.0)
    # The best-rep strategy drifts up so this allocator finishes profitable.
    assert report.total_return > 0


def test_two_allocators_diverge_on_same_input() -> None:
    cfg = BacktestConfig(capital=50_000, period=f"{_PERIOD_DAYS}d")
    rep = run_backtest(ReputationOnlyAllocator(), _universe(), cfg)
    fee = run_backtest(FeeAverseAllocator(), _universe(), cfg)
    # The whole point of the harness: same inputs, different outputs.
    assert rep.final_nav != pytest.approx(fee.final_nav, rel=1e-6)
    # The rep-weighted allocator overweights `0xalpha` (drifts up) so
    # it's hard to beat on a straight reputation race.
    assert rep.fills_by_strategy["0xalpha"] >= fee.fills_by_strategy["0xalpha"]


def test_short_nav_series_raises() -> None:
    cfg = BacktestConfig(capital=10_000, period=f"{_PERIOD_DAYS}d")
    short = StrategyNavSeries(
        strategy_id="0xshort",
        declared_class="momentum_v1",
        fee_rate_bps=2_000,
        stake_amount_usd=10_000,
        max_capacity_usd=200_000,
        reputation_score=0.5,
        daily_navs=tuple(_drifting(100.0, 0.002, 5)),  # only 6 samples
    )
    with pytest.raises(ValueError, match="NAV samples"):
        run_backtest(ReputationOnlyAllocator(), [short], cfg)


def test_empty_universe_raises() -> None:
    with pytest.raises(ValueError, match="at least one strategy"):
        run_backtest(ReputationOnlyAllocator(), [], BacktestConfig())


def test_allocator_fee_takes_a_cut_above_hwm() -> None:
    # All-up trace: every day the strategy gains 0.5%, so the user
    # crosses HWM constantly. Fee-paid should be > 0.
    up = StrategyNavSeries(
        strategy_id="0xup",
        declared_class="momentum_v1",
        fee_rate_bps=2_000,
        stake_amount_usd=10_000,
        max_capacity_usd=500_000,
        reputation_score=1.0,
        daily_navs=tuple(_drifting(100.0, 0.005, _PERIOD_DAYS)),
    )
    cfg = BacktestConfig(
        capital=50_000,
        period=f"{_PERIOD_DAYS}d",
        fee_threshold_bps=100,  # 1% — easy to cross daily
    )
    report = run_backtest(ReputationOnlyAllocator(), [up], cfg)
    assert report.allocator_fees_paid > 0
    assert report.final_nav < 50_000 * (1.005**_PERIOD_DAYS)


def test_render_markdown_contains_headline_metrics() -> None:
    cfg = BacktestConfig(capital=50_000, period=f"{_PERIOD_DAYS}d")
    report = run_backtest(ReputationOnlyAllocator(), _universe(), cfg)
    md = render_markdown(report)
    assert "# Backtest" in md
    assert "RepOnly" in md
    assert "Sharpe" in md
    assert "Max drawdown" in md
    assert "0xalpha" in md  # per-strategy fill table


def test_render_json_round_trip() -> None:
    cfg = BacktestConfig(capital=50_000, period=f"{_PERIOD_DAYS}d")
    report = run_backtest(ReputationOnlyAllocator(), _universe(), cfg)
    payload = json.loads(render_json(report))
    assert payload["allocator_name"] == "RepOnly"
    assert payload["period_days"] == _PERIOD_DAYS
    assert isinstance(payload["daily_nav"], list)
    assert len(payload["daily_nav"]) == _PERIOD_DAYS + 1
