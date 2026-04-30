"""Tests for NAVTracker, max_drawdown, sharpe_ratio."""

from __future__ import annotations

import math

import pytest
from helios.nav import BARS_PER_YEAR_1M, NAVTracker, max_drawdown, sharpe_ratio


def test_initial_nav_must_be_positive() -> None:
    with pytest.raises(ValueError, match="initial_nav"):
        NAVTracker(initial_nav=0.0)


def test_record_appends_navs_and_returns() -> None:
    t = NAVTracker(initial_nav=100.0)
    t.record(110.0)
    t.record(99.0)
    assert t.navs == [100.0, 110.0, 99.0]
    assert t.returns == pytest.approx([0.10, -0.10], rel=1e-9)
    assert t.current == 99.0


def test_peak_is_monotonic() -> None:
    t = NAVTracker(initial_nav=100.0)
    t.record(120.0)
    t.record(80.0)
    t.record(110.0)
    assert t.peak == 120.0


def test_max_drawdown_tracks_worst_peak_to_trough() -> None:
    t = NAVTracker(initial_nav=100.0)
    t.record(120.0)
    t.record(60.0)  # 50% dd from peak 120
    t.record(90.0)
    assert t.max_drawdown == pytest.approx(0.5, rel=1e-9)


def test_total_return_uses_first_and_last_nav() -> None:
    t = NAVTracker(initial_nav=100.0)
    t.record(150.0)
    assert t.total_return == pytest.approx(0.5, rel=1e-9)


def test_sharpe_zero_with_fewer_than_two_returns() -> None:
    t = NAVTracker(initial_nav=100.0)
    assert t.sharpe() == 0.0
    t.record(101.0)
    assert t.sharpe() == 0.0


def test_sharpe_zero_when_returns_have_zero_stdev() -> None:
    t = NAVTracker(initial_nav=100.0)
    t.record(110.0)
    t.record(121.0)  # +10% each bar — constant return → 0 stdev
    assert t.sharpe() == 0.0


def test_sharpe_positive_for_steady_uptrend_with_noise() -> None:
    t = NAVTracker(initial_nav=100.0, bars_per_year=BARS_PER_YEAR_1M)
    nav = 100.0
    for _ in range(50):
        nav *= 1.001
        t.record(nav)
    nav *= 0.9995
    t.record(nav)
    assert t.sharpe() > 0


def test_max_drawdown_standalone() -> None:
    assert max_drawdown([]) == 0.0
    assert max_drawdown([100.0, 110.0, 120.0]) == 0.0
    assert max_drawdown([100.0, 120.0, 60.0, 90.0]) == pytest.approx(0.5)


def test_sharpe_ratio_standalone_matches_tracker() -> None:
    returns = [0.001, 0.002, -0.001, 0.0015, 0.0005]
    standalone = sharpe_ratio(returns, bars_per_year=BARS_PER_YEAR_1M)
    n = len(returns)
    mean = sum(returns) / n
    var = sum((x - mean) ** 2 for x in returns) / (n - 1)
    expected = (mean / math.sqrt(var)) * math.sqrt(BARS_PER_YEAR_1M)
    assert standalone == pytest.approx(expected, rel=1e-9)


def test_sharpe_ratio_short_series_returns_zero() -> None:
    assert sharpe_ratio([]) == 0.0
    assert sharpe_ratio([0.01]) == 0.0
