"""AllocatorSDK helpers — pure-function building blocks for ranking.

Public surface:

    detect_regime, helix_fee_factor      (regime.py — `Helios.md §11.4.1 (a)`)
    pairwise_correlation,
    pairwise_correlation_from_goldsky,
    helix_greedy_pick                    (correlation.py — §11.4.1 (b))
    btc_realized_vol_30d,
    btc_vol_percentiles_1y,
    StaticMarketData, OracleHTTPReader,
    MarketDataReader                      (market_data.py)
    Regime                                (re-exported from `types`)

v1 Helix-lite consumes only `helix_fee_factor`; the remaining helpers
ship for third-party allocators and Helix-v2.
"""

from __future__ import annotations

from helios_allocator.helpers.correlation import (
    helix_greedy_pick,
    pairwise_correlation,
    pairwise_correlation_from_goldsky,
)
from helios_allocator.helpers.market_data import (
    MarketDataReader,
    OracleHTTPReader,
    StaticMarketData,
    btc_realized_vol_30d,
    btc_vol_percentiles_1y,
)
from helios_allocator.helpers.regime import detect_regime, helix_fee_factor
from helios_allocator.types import Regime

__all__ = [
    "MarketDataReader",
    "OracleHTTPReader",
    "Regime",
    "StaticMarketData",
    "btc_realized_vol_30d",
    "btc_vol_percentiles_1y",
    "detect_regime",
    "helix_fee_factor",
    "helix_greedy_pick",
    "pairwise_correlation",
    "pairwise_correlation_from_goldsky",
]
