"""§8.2 worked example, component-by-component, replicated bit-for-bit.

The numerical example matches the block in `Helios.md §8.2` so the test and
spec stay in lockstep. Any change to the formula here MUST update the spec
(and vice versa).
"""

from __future__ import annotations

import math

import pytest
from reputation.cohort import cohort_stats
from reputation.score import (
    W_AGE,
    W_PERF,
    W_PERF_7D,
    W_PERF_30D,
    W_PERF_90D,
    W_PROOF,
    W_RISK,
    W_STAKE,
    CohortContext,
    ScoreInputs,
    WindowSharpe,
    annualized_sharpe_from_nav,
    compute_score,
    hash_components,
)


def _example_cohort() -> CohortContext:
    # Cohort of 2 strategies per window → median=1.5, IQR=range=1.0 across all windows.
    s = cohort_stats([1.0, 2.0])
    return CohortContext(win_7d=s, win_30d=s, win_90d=s)


def _example_inputs() -> ScoreInputs:
    return ScoreInputs(
        sharpes=WindowSharpe(sharpe_7d=2.5, sharpe_30d=2.0, sharpe_90d=1.8),
        max_drawdown_bps_90d=1500,
        valid_proofs=199,
        total_proof_attempts=200,
        stake_e18=5_000 * 10**18,
        max_stake_in_class_e18=50_000 * 10**18,
        trades_attested=250,
    )


def test_weights_sum_to_one() -> None:
    assert W_PERF + W_RISK + W_PROOF + W_STAKE + W_AGE == 1.0
    assert W_PERF_7D + W_PERF_30D + W_PERF_90D == 1.0


def test_performance_component_normalized_then_clipped() -> None:
    out = compute_score(_example_inputs(), _example_cohort())
    # norm_7d = (2.5-1.5)/1.0 = 1.0
    # norm_30d = (2.0-1.5)/1.0 = 0.5
    # norm_90d = (1.8-1.5)/1.0 = 0.3
    # perf = 0.5·1.0 + 0.3·0.5 + 0.2·0.3 = 0.71
    assert math.isclose(out.components.performance, 0.71, rel_tol=1e-9)
    assert math.isclose(out.perf_breakdown.norm_7d, 1.0)
    assert math.isclose(out.perf_breakdown.norm_30d, 0.5)
    assert math.isclose(out.perf_breakdown.norm_90d, 0.3)


def test_risk_score_linear_in_drawdown() -> None:
    out = compute_score(_example_inputs(), _example_cohort())
    # 1 - clip(1500 / 5000, 0, 1) = 0.7
    assert math.isclose(out.components.risk, 0.7)


def test_proof_score_is_pure_ratio() -> None:
    out = compute_score(_example_inputs(), _example_cohort())
    assert math.isclose(out.components.proof, 199 / 200)


def test_stake_score_log_curve() -> None:
    out = compute_score(_example_inputs(), _example_cohort())
    # log(1 + 5000/1000) / log(1 + 50000/1000) = log(6)/log(51)
    assert math.isclose(out.components.stake, math.log(6) / math.log(51), rel_tol=1e-9)


def test_age_score_sqrt_curve() -> None:
    out = compute_score(_example_inputs(), _example_cohort())
    # sqrt(250 / 1000) = 0.5
    assert math.isclose(out.components.age, 0.5)


def test_aggregate_score_e4() -> None:
    out = compute_score(_example_inputs(), _example_cohort())
    perf = 0.71
    risk = 0.7
    proof = 199 / 200
    stake = math.log(6) / math.log(51)
    age = 0.5
    expected = W_PERF * perf + W_RISK * risk + W_PROOF * proof + W_STAKE * stake + W_AGE * age
    assert out.score_e4 == round(10_000 * expected)


def test_components_hash_is_stable_32_bytes() -> None:
    out = compute_score(_example_inputs(), _example_cohort())
    assert len(out.components_hash) == 32
    again = hash_components(out.components)
    assert again == out.components_hash


def test_negative_performance_when_below_cohort() -> None:
    cohort = _example_cohort()
    inputs = ScoreInputs(
        sharpes=WindowSharpe(sharpe_7d=0.5, sharpe_30d=0.5, sharpe_90d=0.5),
        max_drawdown_bps_90d=0,
        valid_proofs=10,
        total_proof_attempts=10,
        stake_e18=10**18,
        max_stake_in_class_e18=10**18,
        trades_attested=0,
    )
    out = compute_score(inputs, cohort)
    # All windows: (0.5 - 1.5) / 1.0 = -1.0 → perf raw = -1.0 → clip → -1.0
    assert math.isclose(out.components.performance, -1.0)


def test_score_bounded_in_e4_range() -> None:
    # Stress: max-out every component on the upside.
    cohort = _example_cohort()
    inputs = ScoreInputs(
        sharpes=WindowSharpe(sharpe_7d=100.0, sharpe_30d=100.0, sharpe_90d=100.0),
        max_drawdown_bps_90d=0,
        valid_proofs=10_000,
        total_proof_attempts=10_000,
        stake_e18=10**24,
        max_stake_in_class_e18=10**24,
        trades_attested=10_000,
    )
    out = compute_score(inputs, cohort)
    assert -10_000 <= out.score_e4 <= 10_000


@pytest.mark.parametrize(
    "trades, valid, expected",
    [
        (1000, 1000, 1.0),
        (1, 0, 0.0),
        (0, 0, 0.0),
    ],
)
def test_proof_score_edge_cases(trades: int, valid: int, expected: float) -> None:
    cohort = _example_cohort()
    inputs = ScoreInputs(
        sharpes=WindowSharpe(0.0, 0.0, 0.0),
        max_drawdown_bps_90d=0,
        valid_proofs=valid,
        total_proof_attempts=trades,
        stake_e18=0,
        max_stake_in_class_e18=10**18,
        trades_attested=trades,
    )
    out = compute_score(inputs, cohort)
    assert math.isclose(out.components.proof, expected)


def test_annualized_sharpe_zero_for_constant_nav() -> None:
    series = [(86_400 * d, 10**18) for d in range(10)]
    assert annualized_sharpe_from_nav(series) == 0.0


def test_annualized_sharpe_handles_short_series() -> None:
    assert annualized_sharpe_from_nav([(0, 10**18)]) == 0.0
    assert annualized_sharpe_from_nav([]) == 0.0


def test_annualized_sharpe_positive_with_realistic_noise() -> None:
    # Trending NAV with day-to-day noise → positive but finite Sharpe.
    series = [
        (86_400 * d, int(10**18 * (1.001**d) * (1 + 0.0005 * ((d % 3) - 1))))
        for d in range(20)
    ]
    assert annualized_sharpe_from_nav(series) > 0.0


def test_annualized_sharpe_negative_with_declining_nav() -> None:
    series = [
        (86_400 * d, int(10**18 * (0.999**d) * (1 + 0.0005 * ((d % 3) - 1))))
        for d in range(20)
    ]
    assert annualized_sharpe_from_nav(series) < 0.0
