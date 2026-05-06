"""Tests for the SDK's yield_rotation_v1 backtest driver (WS4 PR 1/3).

Covers:
  * Running a YR strategy through `run_yield_backtest` produces a
    coherent rotation list, average APY, and bridging-cost charge.
  * The driver rejects non-YR strategies and empty tick streams.
  * `m_from` mismatch with `active_market` raises (after the first
    rotation has happened).
  * The standalone reference impl is bridged onto the SDK driver and
    produces non-zero rotations on a synthetic divergence.
"""

from __future__ import annotations

import math

import pytest
from helios import (
    MarketSnapshot,
    RotationIntent,
    StrategyAgent,
    TradeIntent,
    YieldBacktestReport,
    YieldTick,
    run_yield_backtest,
)


class _ChasingYR(StrategyAgent):
    """Tiny YR strategy that always rotates to the highest-APY market
    above a fixed threshold. Used by the driver tests so we don't pull
    the reference impl into the SDK test surface."""

    declared_class = "yield_rotation_v1"
    asset_universe = ()
    max_position_size_usd = 50_000
    fee_rate_bps = 1_500

    def __init__(
        self,
        *,
        allowlisted_markets: tuple[int, ...] = (1, 2, 3, 4),
        signal_threshold_bps: int = 80,
    ) -> None:
        super().__init__()
        self._allowlist = allowlisted_markets
        self._signal_threshold_bps = signal_threshold_bps

    def on_bar(self, asset: str, snapshot: MarketSnapshot) -> TradeIntent | None:
        del asset, snapshot
        return None

    def on_yield_tick(self, ticks: dict[int, YieldTick]) -> RotationIntent | None:
        candidates = {m: t for m, t in ticks.items() if m in self._allowlist}
        if len(candidates) < 2:
            return None
        best = max(candidates, key=lambda m: candidates[m].apy_bps_e6)
        worst = min(candidates, key=lambda m: candidates[m].apy_bps_e6)
        if self.active_market == best:
            return None
        m_from = self.active_market if self.active_market in candidates else worst
        diff_bps_e6 = candidates[best].apy_bps_e6 - candidates[m_from].apy_bps_e6
        diff_bps = diff_bps_e6 // 1_000_000
        if diff_bps < self._signal_threshold_bps:
            return None
        return RotationIntent(
            m_from=m_from,
            m_to=best,
            amount_in_usd=10_000.0,
            apy_from_bps=candidates[m_from].apy_bps_e6 // 1_000_000,
            apy_to_bps=candidates[best].apy_bps_e6 // 1_000_000,
        )


def _ticks(curves: dict[int, list[int]]) -> list[dict[int, YieldTick]]:
    """Turn `{market_id: [apy_bps per tick]}` into the SDK tick shape."""
    n = next(iter(curves.values()))
    return [
        {
            m: YieldTick(
                market_id=m, apy_bps_e6=curves[m][i] * 1_000_000, timestamp_ms=i * 3_600_000
            )
            for m in curves
        }
        for i in range(len(n))
    ]


# ─── shape ─────────────────────────────────────────────────


def test_run_yield_backtest_basic_shape() -> None:
    # Market 2 dominates; a chasing strategy will rotate into it once
    # and then stay there.
    curves = {1: [300] * 50, 2: [600] * 50}
    report = run_yield_backtest(
        strategy=_ChasingYR(allowlisted_markets=(1, 2)),
        ticks=_ticks(curves),
        initial_capital=10_000.0,
        tick_interval_sec=3_600,
        bridging_cost_bps=0,
    )
    assert isinstance(report, YieldBacktestReport)
    assert report.ticks == 50
    # Exactly one rotation: m_from=1 (worst at deploy time), m_to=2.
    assert len(report.rotations) == 1
    assert report.rotations[0].m_from == 1
    assert report.rotations[0].m_to == 2
    assert report.rotations[0].apy_to_bps - report.rotations[0].apy_from_bps == 300
    assert report.rotations_with_pos_diff == 1
    # 49 ticks at 600 bps APY of 10k initial capital, hourly:
    # 10_000 * 0.06 * (49 * 3600 / (365*24*3600)) ≈ $3.36
    expected = 10_000 * 0.06 * (49 * 3600 / (365 * 24 * 3600))
    assert math.isclose(report.realized_yield_usd, expected, rel_tol=1e-6)


def test_run_yield_backtest_average_apy_matches_realised() -> None:
    curves = {1: [400] * 100, 2: [400] * 100}
    report = run_yield_backtest(
        strategy=_ChasingYR(allowlisted_markets=(1, 2), signal_threshold_bps=10_000),
        ticks=_ticks(curves),
        initial_capital=10_000.0,
        tick_interval_sec=3_600,
    )
    # Threshold is unreachable → no rotation, no active market, no
    # realized yield. Average APY collapses to zero.
    assert report.rotations == []
    assert report.realized_yield_usd == 0.0
    assert report.avg_active_apy_bps == 0.0


def test_run_yield_backtest_bridging_cost_charged_per_rotation() -> None:
    # Alternate which market is best every 24 ticks → forces multiple
    # rotations. With bridging_cost_bps=200 (2%), each rotation costs
    # 2% × initial_capital = $200.
    n = 96
    curves = {
        1: [800 if (i // 24) % 2 == 0 else 100 for i in range(n)],
        2: [100 if (i // 24) % 2 == 0 else 800 for i in range(n)],
    }
    no_cost = run_yield_backtest(
        strategy=_ChasingYR(allowlisted_markets=(1, 2)),
        ticks=_ticks(curves),
        initial_capital=10_000.0,
        bridging_cost_bps=0,
    )
    with_cost = run_yield_backtest(
        strategy=_ChasingYR(allowlisted_markets=(1, 2)),
        ticks=_ticks(curves),
        initial_capital=10_000.0,
        bridging_cost_bps=200,
    )
    n_rot = len(with_cost.rotations)
    assert n_rot == len(no_cost.rotations) > 1
    # Bridging cost lowers realised yield by exactly $200 per rotation.
    assert math.isclose(
        with_cost.realized_yield_usd,
        no_cost.realized_yield_usd - n_rot * 200.0,
        rel_tol=1e-9,
    )
    assert with_cost.bridging_cost_total_bps == n_rot * 200


# ─── error paths ───────────────────────────────────────────


def test_run_yield_backtest_rejects_non_yr_strategy() -> None:
    class _Mom(StrategyAgent):
        declared_class = "momentum_v1"
        asset_universe = ("BTC",)
        max_position_size_usd = 100
        fee_rate_bps = 0

        def on_bar(self, asset: str, snapshot: MarketSnapshot) -> TradeIntent | None:
            del asset, snapshot
            return None

    with pytest.raises(ValueError, match="yield_rotation_v1"):
        run_yield_backtest(strategy=_Mom(), ticks=[{1: YieldTick(1, 0, 0)}])


def test_run_yield_backtest_rejects_empty_ticks() -> None:
    with pytest.raises(ValueError, match="ticks must not be empty"):
        run_yield_backtest(strategy=_ChasingYR(), ticks=[])


def test_run_yield_backtest_rejects_bad_interval() -> None:
    with pytest.raises(ValueError, match="tick_interval_sec must be positive"):
        run_yield_backtest(
            strategy=_ChasingYR(),
            ticks=[{1: YieldTick(1, 0, 0)}],
            tick_interval_sec=0,
        )


def test_driver_rejects_phantom_m_from() -> None:
    """Once active_market is set, the strategy must rotate from there."""

    class _LiarYR(_ChasingYR):
        # Override to always claim m_from=99 — a market that doesn't
        # exist in the snapshot. The driver should reject the rotation
        # rather than silently advancing through a nonsense state.
        def on_yield_tick(self, ticks: dict[int, YieldTick]) -> RotationIntent | None:
            if self.active_market is None:
                # Allowed: initial deployment picks any m_from.
                return super().on_yield_tick(ticks)
            return RotationIntent(
                m_from=99,
                m_to=2,
                amount_in_usd=10_000.0,
                apy_from_bps=100,
                apy_to_bps=200,
            )

    curves = {1: [200, 200, 200, 200, 200], 2: [800, 800, 200, 200, 200]}
    with pytest.raises(RuntimeError, match="m_from=99"):
        run_yield_backtest(
            strategy=_LiarYR(allowlisted_markets=(1, 2)),
            ticks=_ticks(curves),
            tick_interval_sec=3_600,
        )


# ─── reference impl plays nicely with the driver ────────────


def test_driver_plays_with_reference_yr_strategy() -> None:
    """The reference YR strategy ships its own `_active_market` and
    `set_active_market`; the SDK driver should still drive it without
    changes — that's the contract for keeping `services/sentinel`-style
    consumers stable across the WS4 lift."""

    yr_module = pytest.importorskip("yield_rotation_v1")
    strategy = yr_module.YieldRotationStrategy(
        allowlisted_markets=(1, 2, 3),
        signal_threshold_bps=80,
        bridging_cost_bps=30,
    )
    strategy.set_capital(50_000.0)

    curves = {
        1: [300 + (10 if i % 5 == 0 else 0) for i in range(72)],
        2: [600 + (5 if i % 7 == 0 else 0) for i in range(72)],
        3: [350 + (i // 36) * 400 for i in range(72)],  # market 3 jumps mid-run
    }
    report = run_yield_backtest(
        strategy=strategy,
        ticks=_ticks(curves),
        initial_capital=50_000.0,
        tick_interval_sec=3_600,
        bridging_cost_bps=30,
    )
    # The strategy should rotate at least once into market 2 (highest
    # at start) and then react when market 3 jumps. Both events are
    # past the 80+30 bps net threshold.
    assert len(report.rotations) >= 2
    market_to_set = {r.m_to for r in report.rotations}
    assert 2 in market_to_set
    assert 3 in market_to_set
