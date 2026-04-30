"""Strategy-layer invariants for `YieldRotationStrategy.on_yield_tick`.

Tests the rotation decision in isolation — no oracle, no prover, no
witness builder. The runtime tests exercise the full chain.
"""

from __future__ import annotations

import pytest

from yield_rotation_v1.strategy import YieldRotationStrategy
from yield_rotation_v1.types import YieldTick


# Helper — APY in plain bps × 1e6 (matches YieldStore convention).
def tick(market_id: int, apy_bps: int, ts: int = 1_000_000_000) -> YieldTick:
    return YieldTick(
        market_id=market_id, apy_bps_e6=apy_bps * 1_000_000, timestamp_ms=ts
    )


def test_rotates_when_differential_clears_threshold_and_bridging() -> None:
    s = YieldRotationStrategy(
        allowlisted_markets=(1, 2),
        signal_threshold_bps=80,
        bridging_cost_bps=30,
    )
    s.set_capital(10_000)
    s.set_active_market(1)
    intent = s.on_yield_tick({1: tick(1, 420), 2: tick(2, 550)})
    assert intent is not None
    assert intent.m_from == 1
    assert intent.m_to == 2
    assert intent.apy_from_bps == 420
    assert intent.apy_to_bps == 550


def test_holds_when_differential_below_threshold_plus_bridging() -> None:
    s = YieldRotationStrategy(
        allowlisted_markets=(1, 2),
        signal_threshold_bps=80,
        bridging_cost_bps=30,
    )
    s.set_capital(10_000)
    s.set_active_market(1)
    # 109 bps differential ⇒ below 80 + 30 = 110 required
    intent = s.on_yield_tick({1: tick(1, 420), 2: tick(2, 529)})
    assert intent is None


def test_holds_when_already_in_best_market() -> None:
    s = YieldRotationStrategy(
        allowlisted_markets=(1, 2),
        signal_threshold_bps=80,
        bridging_cost_bps=30,
    )
    s.set_capital(10_000)
    s.set_active_market(2)  # already in compound (best APY)
    intent = s.on_yield_tick({1: tick(1, 420), 2: tick(2, 550)})
    assert intent is None


def test_ignores_non_allowlisted_markets() -> None:
    s = YieldRotationStrategy(
        allowlisted_markets=(1, 2),
        signal_threshold_bps=80,
        bridging_cost_bps=30,
    )
    s.set_capital(10_000)
    s.set_active_market(1)
    # Market 3 has highest APY but isn't allowlisted ⇒ ignored.
    intent = s.on_yield_tick(
        {1: tick(1, 420), 2: tick(2, 550), 3: tick(3, 800)}
    )
    assert intent is not None
    assert intent.m_to == 2  # best of allowlisted, not 3


def test_holds_when_only_one_allowlisted_in_tick() -> None:
    s = YieldRotationStrategy(
        allowlisted_markets=(1, 2),
        signal_threshold_bps=80,
        bridging_cost_bps=30,
    )
    s.set_capital(10_000)
    intent = s.on_yield_tick({1: tick(1, 420), 99: tick(99, 800)})
    assert intent is None


def test_no_rotation_with_empty_ticks() -> None:
    s = YieldRotationStrategy(allowlisted_markets=(1, 2))
    assert s.on_yield_tick({}) is None


def test_initial_rotation_picks_worst_as_source() -> None:
    """No active market yet — strategy should pick worst-apy allowlisted
    as the from leg so the differential is maximally proven."""
    s = YieldRotationStrategy(
        allowlisted_markets=(1, 2, 3),
        signal_threshold_bps=80,
        bridging_cost_bps=30,
    )
    s.set_capital(10_000)
    intent = s.on_yield_tick(
        {1: tick(1, 420), 2: tick(2, 550), 3: tick(3, 380)}
    )
    assert intent is not None
    assert intent.m_from == 3  # worst APY
    assert intent.m_to == 2  # best APY


def test_constructor_validates_threshold_and_cost() -> None:
    with pytest.raises(ValueError):
        YieldRotationStrategy(allowlisted_markets=(1,), signal_threshold_bps=-1)
    with pytest.raises(ValueError):
        YieldRotationStrategy(allowlisted_markets=(1,), bridging_cost_bps=-5)


def test_constructor_rejects_empty_allowlist() -> None:
    with pytest.raises(ValueError, match="allowlisted_markets"):
        YieldRotationStrategy(allowlisted_markets=())


def test_on_bar_is_no_op() -> None:
    """YR doesn't respond to price bars — the base hook is overridden."""
    from datetime import datetime, timezone

    from helios.types import MarketSnapshot

    s = YieldRotationStrategy(allowlisted_markets=(1, 2))
    snap = MarketSnapshot(
        asset="WKITE",
        prices=[1000.0] * 16,
        timestamp=datetime.now(tz=timezone.utc),
    )
    assert s.on_bar("WKITE", snap) is None
