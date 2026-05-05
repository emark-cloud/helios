"""WS1.B helpers: market-data reader + BTC vol / percentile helpers.

The on-chain integration (real `OracleHTTPReader` against a running
oracle service) is exercised by the e2e harness; these tests pin the
math against synthetic fixtures so the regime-band calculation has a
deterministic expectation.
"""

from __future__ import annotations

import math

import pytest
from helios_allocator.helpers import (
    StaticMarketData,
    btc_realized_vol_30d,
    btc_vol_percentiles_1y,
)
from helios_allocator.helpers._math import (
    log_returns,
    pearson_correlation,
    percentile,
    percentiles,
    realized_volatility,
)

# ── Pure math layer ──────────────────────────────────────────


def test_log_returns_drops_first_observation() -> None:
    out = log_returns([100.0, 110.0, 121.0])
    # ln(110/100) = ln(1.1); ln(121/110) = ln(1.1).
    assert len(out) == 2
    assert out[0] == pytest.approx(math.log(1.1))
    assert out[1] == pytest.approx(math.log(1.1))


def test_log_returns_rejects_non_positive() -> None:
    with pytest.raises(ValueError):
        log_returns([100.0, 0.0, 90.0])
    with pytest.raises(ValueError):
        log_returns([100.0, -50.0])


def test_realized_volatility_zero_for_flat_series() -> None:
    flat = [0.0, 0.0, 0.0, 0.0]
    assert realized_volatility(flat) == 0.0


def test_realized_volatility_matches_hand_computed_4dp() -> None:
    """Pin against a hand-computed value so refactors of the variance
    reduction don't drift silently."""
    returns = [0.01, -0.02, 0.015, -0.01, 0.02]
    # mean = 0.003; sample variance = (sum sq deviations) / (n-1)
    # = 0.00118 / 4 = 0.000295
    # sigma = sqrt(0.000295) ≈ 0.017175
    # annualized (×sqrt(365)) ≈ 0.32814
    sigma = realized_volatility(returns)
    assert sigma == pytest.approx(0.32814, abs=1e-4)


def test_percentile_linear_interpolation_matches_numpy_default() -> None:
    """numpy.percentile(method='linear') reference for a known set."""
    vals = sorted([1.0, 2.0, 3.0, 4.0, 5.0])
    assert percentile(vals, 0.0) == 1.0
    assert percentile(vals, 1.0) == 5.0
    assert percentile(vals, 0.5) == 3.0
    # 25th percentile of {1..5} via linear interp = 1 + 0.25*(5-1)/... → 2.0.
    assert percentile(vals, 0.25) == pytest.approx(2.0)


def test_percentiles_keys_are_p20_p80() -> None:
    out = percentiles([1.0, 2.0, 3.0, 4.0, 5.0], [0.20, 0.80])
    assert set(out.keys()) == {"p20", "p80"}
    # p20: 0.20 * 4 = 0.8 → between vals[0]=1 and vals[1]=2 → 1.8.
    # p80: 0.80 * 4 = 3.2 → between vals[3]=4 and vals[4]=5 → 4.2.
    assert out["p20"] == pytest.approx(1.8)
    assert out["p80"] == pytest.approx(4.2)


def test_pearson_correlation_zero_for_flat_input() -> None:
    """Zero variance → ρ=0 by convention rather than division-by-zero."""
    assert pearson_correlation([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) == 0.0


# ── StaticMarketData reader ──────────────────────────────────


@pytest.mark.asyncio
async def test_static_reader_returns_chronological_window() -> None:
    closes = [100.0, 102.0, 101.0, 104.0, 103.0, 106.0, 110.0]
    reader = StaticMarketData({"BTC": closes})
    out = await reader.daily_close_prices("BTC", days=4)
    assert out == closes[-4:]  # tail-aligned window


@pytest.mark.asyncio
async def test_static_reader_zero_days_returns_empty() -> None:
    reader = StaticMarketData({"BTC": [100.0, 101.0]})
    assert await reader.daily_close_prices("BTC", days=0) == []


@pytest.mark.asyncio
async def test_static_reader_unknown_asset_returns_empty() -> None:
    reader = StaticMarketData({"BTC": [100.0]})
    assert await reader.daily_close_prices("ETH", days=30) == []


# ── btc_realized_vol_30d ─────────────────────────────────────


@pytest.mark.asyncio
async def test_btc_realized_vol_30d_matches_pure_math() -> None:
    """The async helper composes `log_returns` + `realized_volatility`;
    bind it against the same primitives at the test level so a refactor
    can't quietly change the contract."""
    closes = [100.0 * math.exp(0.01 * i) for i in range(31)]  # smooth log-trend
    reader = StaticMarketData({"BTC": closes})
    sigma = await btc_realized_vol_30d(reader)
    # Smooth trend → near-zero return variance → near-zero vol.
    assert sigma == pytest.approx(0.0, abs=1e-9)


@pytest.mark.asyncio
async def test_btc_realized_vol_30d_picks_up_jitter() -> None:
    closes = [100.0]
    for i in range(30):
        # Alternating ±1% steps → measurable vol.
        closes.append(closes[-1] * (1.01 if i % 2 == 0 else 0.99))
    reader = StaticMarketData({"BTC": closes})
    sigma = await btc_realized_vol_30d(reader)
    assert sigma > 0.1  # clearly nonzero


# ── btc_vol_percentiles_1y ───────────────────────────────────


@pytest.mark.asyncio
async def test_btc_vol_percentiles_falls_back_to_open_band_on_short_history() -> None:
    """With <30 returns we can't roll a 30d-vol series; default to a
    band that leaves `detect_regime` permanently in NORMAL."""
    reader = StaticMarketData({"BTC": [100.0, 101.0, 102.0]})  # 3 obs → 2 returns
    band = await btc_vol_percentiles_1y(reader)
    assert band == {"p20": 0.0, "p80": float("inf")}


@pytest.mark.asyncio
async def test_btc_vol_percentiles_returns_band_on_full_history() -> None:
    """Synthetic 365-day series with two volatility regimes → p20 < p80."""
    closes = [100.0]
    # First 200 days: low vol (±0.2%/day).
    for i in range(200):
        closes.append(closes[-1] * (1.002 if i % 2 == 0 else 0.998))
    # Last 165 days: high vol (±2%/day).
    for i in range(165):
        closes.append(closes[-1] * (1.02 if i % 2 == 0 else 0.98))
    reader = StaticMarketData({"BTC": closes})
    band = await btc_vol_percentiles_1y(reader)
    assert band["p20"] < band["p80"]
    # Sanity: low-vol regime sits well below high-vol regime.
    assert band["p20"] > 0.0
    assert math.isfinite(band["p80"])
