"""WS1.B helpers: regime detection + Helix fee-factor."""

from __future__ import annotations

import pytest
from helios_allocator.helpers import detect_regime, helix_fee_factor
from helios_allocator.types import Regime

# ── detect_regime ─────────────────────────────────────────────


def test_detect_regime_picks_high_vol_at_or_above_p80() -> None:
    perc = {"p20": 0.40, "p80": 0.80}
    assert detect_regime(0.95, perc) == Regime.HIGH_VOL
    # Boundary: vol exactly at p80 is HIGH_VOL (`>=` per §11.4.1).
    assert detect_regime(0.80, perc) == Regime.HIGH_VOL


def test_detect_regime_picks_low_vol_at_or_below_p20() -> None:
    perc = {"p20": 0.40, "p80": 0.80}
    assert detect_regime(0.10, perc) == Regime.LOW_VOL
    assert detect_regime(0.40, perc) == Regime.LOW_VOL


def test_detect_regime_falls_back_to_normal_in_band() -> None:
    perc = {"p20": 0.40, "p80": 0.80}
    assert detect_regime(0.60, perc) == Regime.NORMAL


# ── helix_fee_factor ──────────────────────────────────────────


def test_helix_fee_factor_hard_caps_above_user_max() -> None:
    """Strategy fee strictly above user cap → 0, regardless of regime."""
    for r in Regime:
        assert helix_fee_factor(2_600, 2_500, r) == 0.0


def test_helix_fee_factor_returns_zero_when_user_max_is_zero() -> None:
    """A user with max_fee_rate_bps=0 has accepted no allocator. Don't
    divide-by-zero; just return 0."""
    assert helix_fee_factor(0, 0, Regime.NORMAL) == 0.0


def test_helix_fee_factor_monotonic_in_headroom() -> None:
    """All else equal, lower strategy fee → higher fee factor in every regime."""
    for r in Regime:
        cheaper = helix_fee_factor(500, 2_500, r)
        pricier = helix_fee_factor(2_000, 2_500, r)
        assert cheaper >= pricier, f"{r}: cheaper={cheaper} pricier={pricier}"


def test_helix_fee_factor_high_vol_punishes_high_fees_harder() -> None:
    """HIGH_VOL uses sqrt(headroom); for the same fee level it should
    sit between LOW_VOL and zero. The piecewise shape means HIGH_VOL is
    sharper-falling than LOW_VOL as headroom shrinks."""
    # Strategy at 90% of cap → 10% headroom.
    h = helix_fee_factor(2_250, 2_500, Regime.HIGH_VOL)
    n = helix_fee_factor(2_250, 2_500, Regime.NORMAL)
    low = helix_fee_factor(2_250, 2_500, Regime.LOW_VOL)
    # At small headroom: NORMAL (0.3 + 0.7*0.1=0.37) and LOW_VOL (0.5+0.05=0.55)
    # are floor-supported; HIGH_VOL (sqrt(0.1)≈0.316) drops below NORMAL.
    assert h < n < low


def test_helix_fee_factor_returns_full_value_at_zero_fee() -> None:
    """Free strategy → headroom = 1 → ceiling for each regime."""
    assert helix_fee_factor(0, 2_500, Regime.HIGH_VOL) == pytest.approx(1.0)
    assert helix_fee_factor(0, 2_500, Regime.NORMAL) == pytest.approx(1.0)
    assert helix_fee_factor(0, 2_500, Regime.LOW_VOL) == pytest.approx(1.0)


def test_helix_fee_factor_floor_support_in_low_and_normal() -> None:
    """LOW_VOL floor is 0.5, NORMAL floor is 0.3 (both at zero headroom).
    HIGH_VOL has no floor — sqrt(0) = 0."""
    floor_high = helix_fee_factor(2_500, 2_500, Regime.HIGH_VOL)
    floor_normal = helix_fee_factor(2_500, 2_500, Regime.NORMAL)
    floor_low = helix_fee_factor(2_500, 2_500, Regime.LOW_VOL)
    assert floor_high == pytest.approx(0.0)
    assert floor_normal == pytest.approx(0.3)
    assert floor_low == pytest.approx(0.5)
