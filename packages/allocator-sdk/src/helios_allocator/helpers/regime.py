"""Regime detection + Helix fee-factor.

Spec: `Helios.md §11.4.1 (a)`.

v1 Helix-lite pins regime to `Regime.NORMAL` (see `Helios.md §11.4`
callout). These helpers ship in v1 so any third-party allocator can
adopt regime adaptivity earlier than Helix does; Helix-v2 wires the
hooks up via `BaseAllocator.market_data`.
"""

from __future__ import annotations

from collections.abc import Mapping

from helios_allocator.types import Regime


def detect_regime(
    btc_realized_vol_30d: float,
    historical_percentiles: Mapping[str, float],
) -> Regime:
    """Map current 30-day BTC realized vol into a regime bucket using a
    1-year percentile reference window. `historical_percentiles` must
    expose the keys `"p20"` and `"p80"`.
    """
    p20 = historical_percentiles["p20"]
    p80 = historical_percentiles["p80"]
    if btc_realized_vol_30d >= p80:
        return Regime.HIGH_VOL
    if btc_realized_vol_30d <= p20:
        return Regime.LOW_VOL
    return Regime.NORMAL


def helix_fee_factor(
    strategy_fee_bps: int,
    user_max_fee_bps: int,
    regime: Regime,
) -> float:
    """Continuous fee-fit penalty in [0, 1].

    Hard cap: returns 0 if the strategy fee exceeds the user's max.
    Otherwise scales by available headroom, with regime-specific shape:

        HIGH_VOL: sqrt(headroom)        — favor cheaper strategies sharply
        NORMAL:   0.3 + 0.7 * headroom  — moderate fee preference
        LOW_VOL:  0.5 + 0.5 * headroom  — mild fee preference
    """
    if user_max_fee_bps <= 0:
        return 0.0
    if strategy_fee_bps > user_max_fee_bps:
        return 0.0
    headroom = (user_max_fee_bps - strategy_fee_bps) / user_max_fee_bps
    if regime == Regime.HIGH_VOL:
        return headroom**0.5
    if regime == Regime.LOW_VOL:
        return 0.5 + 0.5 * headroom
    return 0.3 + 0.7 * headroom
