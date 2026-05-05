"""MeanReversionStrategy.on_bar — class invariant cases.

Verifies long entry on N-sigma down, short entry on N-sigma up, exit on
mean re-cross while in position, stop-loss exit, no-signal in flat
market, and that USDC never produces a signal.
"""

from __future__ import annotations

from datetime import UTC, datetime

from helios.types import Direction, MarketSnapshot
from mean_reversion_v1.strategy import LOOKBACK_BARS, MeanReversionStrategy


def _snapshot(asset: str, *, prices: list[float]) -> MarketSnapshot:
    return MarketSnapshot(
        asset=asset,
        timestamp=datetime.now(UTC),
        prices=prices,
        bar_interval_sec=60,
    )


def _flat_with_dip(*, mean: float, dip: float) -> list[float]:
    """16 bars at `mean`, last bar at `mean - dip`. Replicates the
    fixture in `circuits/scripts/gen-fixture-mr.js` (15 × 1000 then 700).
    """
    prices = [mean] * (LOOKBACK_BARS - 1)
    prices.append(mean - dip)
    return prices


def _flat_with_pop(*, mean: float, pop: float) -> list[float]:
    prices = [mean] * (LOOKBACK_BARS - 1)
    prices.append(mean + pop)
    return prices


def test_long_entry_on_n_sigma_down() -> None:
    s = MeanReversionStrategy(n_sigma_x100=200)  # 2.00σ
    s.set_capital(10_000)
    # 15 bars at 1000, last bar at 700 ⇒ |z| ≈ 3.87σ ≥ 2σ ⇒ long entry.
    snap = _snapshot("WETH", prices=_flat_with_dip(mean=1000.0, dip=300.0))
    intent = s.on_bar("WETH", snap)
    assert intent is not None
    assert intent.direction == Direction.LONG
    assert intent.asset_in == "USDC"
    assert intent.asset_out == "WETH"
    assert intent.amount_in_usd is not None
    assert intent.amount_in_usd <= s.max_position_size_usd
    # PR4: exit-only flags must remain False on entries.
    assert intent.is_signal_flip is False
    assert intent.is_stop_loss is False


def test_short_entry_on_n_sigma_up() -> None:
    s = MeanReversionStrategy(n_sigma_x100=200)
    s.set_capital(10_000)
    snap = _snapshot("WETH", prices=_flat_with_pop(mean=1000.0, pop=300.0))
    intent = s.on_bar("WETH", snap)
    assert intent is not None
    assert intent.direction == Direction.SHORT
    assert intent.asset_in == "WETH"
    assert intent.asset_out == "USDC"


def test_no_entry_when_z_below_threshold() -> None:
    s = MeanReversionStrategy(n_sigma_x100=200)
    s.set_capital(10_000)
    # Noisy history with last bar near the mean: |z| ≪ 2σ ⇒ no entry.
    # 8 × 990, 7 × 1010, then 1000 ⇒ stddev ≈ 10, last bar deviation ≈ 0.
    prices = [990.0] * 8 + [1010.0] * 7 + [1000.0]
    snap = _snapshot("WETH", prices=prices)
    assert s.on_bar("WETH", snap) is None


def test_exit_on_mean_recross_when_long() -> None:
    s = MeanReversionStrategy(n_sigma_x100=200)
    s.set_capital(10_000)
    s.set_position("WETH", qty=0.5, avg_price=900.0, direction=Direction.LONG)
    # Price has reverted close to the mean ⇒ |z| < 2σ while we still hold.
    # Need non-zero stddev ⇒ vary the prices slightly. 14 bars at 1000,
    # 1 at 1010, 1 at 1000 ⇒ small spread, last close to mean ⇒ exit.
    prices = [1000.0] * 14 + [1010.0, 1000.0]
    snap = _snapshot("WETH", prices=prices)
    intent = s.on_bar("WETH", snap)
    assert intent is not None
    assert intent.direction == Direction.EXIT
    assert intent.asset_in == "WETH"
    assert intent.asset_out == "USDC"
    assert intent.amount_in_asset == 0.5
    assert intent.is_signal_flip is True
    assert intent.is_stop_loss is False


def test_exit_on_stop_loss_when_long() -> None:
    s = MeanReversionStrategy(n_sigma_x100=200, stop_loss_price_usd=950.0)
    s.set_capital(10_000)
    s.set_position("WETH", qty=0.5, avg_price=1000.0, direction=Direction.LONG)
    # Price has dropped to 940 — below stop. Vary history so stddev > 0.
    prices = [1000.0] * 14 + [990.0, 940.0]
    snap = _snapshot("WETH", prices=prices)
    intent = s.on_bar("WETH", snap)
    assert intent is not None
    assert intent.direction == Direction.EXIT
    assert intent.is_stop_loss is True
    assert intent.is_signal_flip is False


def test_no_exit_when_already_flat() -> None:
    s = MeanReversionStrategy(n_sigma_x100=200)
    s.set_capital(10_000)
    # Tiny perturbation — z is small, no entry, no exit (no position).
    prices = [1000.0] * 14 + [1010.0, 1000.0]
    snap = _snapshot("WETH", prices=prices)
    assert s.on_bar("WETH", snap) is None


def test_usdc_never_signals() -> None:
    s = MeanReversionStrategy(n_sigma_x100=200)
    s.set_capital(10_000)
    snap = _snapshot("USDC", prices=[1.0] * LOOKBACK_BARS)
    assert s.on_bar("USDC", snap) is None


def test_short_history_returns_none() -> None:
    """Circuit needs exactly 16 observations; shorter histories are
    soft-skipped."""
    s = MeanReversionStrategy(n_sigma_x100=200)
    s.set_capital(10_000)
    snap = _snapshot("WETH", prices=[1000.0, 990.0, 700.0])
    assert s.on_bar("WETH", snap) is None


def test_position_fraction_limits_size() -> None:
    s = MeanReversionStrategy(n_sigma_x100=200, position_fraction=0.25)
    s.set_capital(8_000)
    snap = _snapshot("WETH", prices=_flat_with_dip(mean=1000.0, dip=300.0))
    intent = s.on_bar("WETH", snap)
    assert intent is not None
    assert intent.amount_in_usd == 2_000  # 25% of 8k
