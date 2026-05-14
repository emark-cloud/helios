"""MomentumStrategy.on_bar — class invariant cases.

Verifies long-entry trigger, exit on signal flip, and skips on
flat-or-no-signal. Real proof generation is covered in the prover
service's own tests; this module tests the operator-editable surface.
"""

from __future__ import annotations

from datetime import UTC, datetime

from helios.types import Direction, MarketSnapshot
from momentum_v1.strategy import MomentumStrategy


def _snapshot(asset: str, *, prices: list[float]) -> MarketSnapshot:
    return MarketSnapshot(
        asset=asset,
        timestamp=datetime.now(UTC),
        prices=prices,
        bar_interval_sec=60,
    )


def test_long_entry_when_return_exceeds_threshold() -> None:
    s = MomentumStrategy(signal_threshold=0.015, lookback_bars=5)
    s.set_capital(10_000)
    # 5-bar return ≈ +2% > 1.5% threshold
    snap = _snapshot("WETH", prices=[100.0, 100.5, 101.0, 101.5, 102.0, 102.5])
    intent = s.on_bar("WETH", snap)
    assert intent is not None
    assert intent.direction == Direction.LONG
    assert intent.asset_in == "USDC"
    assert intent.asset_out == "WETH"
    assert intent.amount_in_usd is not None
    assert intent.amount_in_usd <= s.max_position_size_usd


def test_no_entry_when_return_below_threshold() -> None:
    s = MomentumStrategy(signal_threshold=0.015, lookback_bars=5)
    s.set_capital(10_000)
    # +0.5% < threshold
    snap = _snapshot("WETH", prices=[100.0, 100.1, 100.2, 100.3, 100.4, 100.5])
    assert s.on_bar("WETH", snap) is None


def test_exit_on_signal_flip_when_long() -> None:
    s = MomentumStrategy(signal_threshold=0.015, lookback_bars=5)
    s.set_capital(10_000)
    s.set_position("WETH", qty=0.5, avg_price=100.0, direction=Direction.LONG)
    # -2% return triggers exit
    snap = _snapshot("WETH", prices=[100.0, 99.5, 99.0, 98.5, 98.0, 97.5])
    intent = s.on_bar("WETH", snap)
    assert intent is not None
    assert intent.direction == Direction.EXIT
    assert intent.asset_in == "WETH"
    assert intent.asset_out == "USDC"
    assert intent.amount_in_asset == 0.5


def test_no_exit_when_already_flat() -> None:
    s = MomentumStrategy(signal_threshold=0.015, lookback_bars=5)
    s.set_capital(10_000)
    snap = _snapshot("WETH", prices=[100.0, 99.5, 99.0, 98.5, 98.0, 97.5])
    assert s.on_bar("WETH", snap) is None


def test_usdc_never_signals() -> None:
    s = MomentumStrategy(signal_threshold=0.015, lookback_bars=5)
    s.set_capital(10_000)
    snap = _snapshot("USDC", prices=[1.0] * 6)
    assert s.on_bar("USDC", snap) is None


def test_position_fraction_limits_size() -> None:
    s = MomentumStrategy(signal_threshold=0.01, lookback_bars=3, position_fraction=0.25)
    s.set_capital(8_000)
    snap = _snapshot("WETH", prices=[100.0, 101.0, 102.0, 103.0])  # +3% > 1%
    intent = s.on_bar("WETH", snap)
    assert intent is not None
    assert intent.amount_in_usd == 2_000  # 25% of 8k


def test_max_position_caps_size() -> None:
    s = MomentumStrategy(signal_threshold=0.01, lookback_bars=3, position_fraction=1.0)
    s.set_capital(50_000)  # 50k available
    snap = _snapshot("WETH", prices=[100.0, 101.0, 102.0, 103.0])
    intent = s.on_bar("WETH", snap)
    assert intent is not None
    # Capped at max_position_size_usd (10_000), not capital × fraction.
    assert intent.amount_in_usd == 10_000


# ── asset_universe override (Base/Arb-scoped deploys) ──────────
def test_default_asset_universe_unchanged() -> None:
    s = MomentumStrategy(signal_threshold=0.015, lookback_bars=10)
    assert s.asset_universe == ("USDC", "WBTC", "WETH", "WSOL")


def test_asset_universe_override_accepted() -> None:
    s = MomentumStrategy(
        signal_threshold=0.015, lookback_bars=10, asset_universe=("USDC", "WETH")
    )
    assert s.asset_universe == ("USDC", "WETH")


def test_asset_universe_must_start_with_usdc() -> None:
    import pytest

    with pytest.raises(ValueError, match="USDC"):
        MomentumStrategy(
            signal_threshold=0.015, lookback_bars=10, asset_universe=("WETH", "USDC")
        )


def test_asset_universe_rejects_empty() -> None:
    import pytest

    with pytest.raises(ValueError, match="USDC"):
        MomentumStrategy(signal_threshold=0.015, lookback_bars=10, asset_universe=())
