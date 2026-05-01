"""Cohort median/IQR + neutral fallback paths."""

from __future__ import annotations

import math

from reputation.cohort import MIN_COHORT_SIZE, cohort_stats, normalize


def test_below_min_cohort_returns_neutral() -> None:
    s = cohort_stats([1.5])
    assert s.is_fallback is True
    assert s.median == 0.0
    assert s.iqr == 1.0
    # With neutral cohort, normalize is identity.
    assert normalize(1.5, s) == 1.5


def test_min_cohort_size_constant() -> None:
    # WS7.B pins the constant at 3 — guards against silent drift.
    assert MIN_COHORT_SIZE == 3


def test_two_strategy_cohort_falls_back_to_raw_sharpe() -> None:
    # n=2 is below MIN_COHORT_SIZE → raw-Sharpe fallback per Helios.md §8.7.
    s = cohort_stats([1.0, 2.0])
    assert s.is_fallback is True
    assert s.median == 0.0
    assert s.iqr == 1.0
    # normalize collapses to identity: (s - 0) / 1 == s.
    assert math.isclose(normalize(1.0, s), 1.0)
    assert math.isclose(normalize(2.0, s), 2.0)


def test_three_strategy_cohort_uses_range_as_iqr_proxy() -> None:
    # Smallest non-fallback cohort. IQR is undefined for n<4; use the range.
    s = cohort_stats([1.0, 1.5, 2.0])
    assert s.is_fallback is False
    assert s.median == 1.5
    assert s.iqr == 1.0  # range = 2.0 - 1.0
    assert math.isclose(normalize(1.0, s), -0.5)
    assert math.isclose(normalize(2.0, s), 0.5)


def test_four_strategy_cohort_uses_classical_iqr() -> None:
    s = cohort_stats([0.0, 1.0, 2.0, 3.0])
    assert s.is_fallback is False
    assert s.median == 1.5
    # Exclusive quartiles for [0,1,2,3]: Q1=0.25, Q3=2.75 → IQR=2.5
    assert math.isclose(s.iqr, 2.5)
    # NormalizedSharpe(2.0) = (2.0 - 1.5) / 2.5 = 0.2
    assert math.isclose(normalize(2.0, s), 0.2)


def test_all_tied_cohort_falls_back_to_neutral_iqr() -> None:
    s = cohort_stats([1.0, 1.0, 1.0])
    assert s.is_fallback is True
    assert s.median == 1.0
    assert s.iqr == 1.0
    # In tied-cohort fallback, normalize still gives 0 for any tied member.
    assert normalize(1.0, s) == 0.0


def test_normalize_is_centered_on_median() -> None:
    s = cohort_stats([0.5, 1.0, 1.5, 2.0, 2.5])
    assert math.isclose(normalize(s.median, s), 0.0)
