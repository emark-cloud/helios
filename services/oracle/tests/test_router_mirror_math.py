"""Decimal converter tests for the oracle->MockSwapRouter price mirror.

Locks down the math by spot-checking realistic prices (BTC $50k, ETH $3k,
SOL $150) at realistic decimals (USDC=6, WBTC=8, WETH=18, SOL=9), as
well as the (in_dec, out_dec) collision cases (in==out, in>out, in<out).
The 5 bps spread direction is verified independently from the mid math.
"""

from __future__ import annotations

import pytest
from oracle.router_mirror_math import (
    DEFAULT_SPREAD_BPS,
    amount_out,
    compute_price_pair,
)

# Test prices: USD * 10^18.
BTC_E18 = 50_000 * 10**18
ETH_E18 = 3_000 * 10**18
SOL_E18 = 150 * 10**18

USDC_DEC = 6
WBTC_DEC = 8
WETH_DEC = 18
WSOL_DEC = 9


def _round_trip(amount_in: int, fwd: tuple[int, int], rev: tuple[int, int]) -> int:
    """Buy then immediately sell — the spread leak is what's left."""
    bought = amount_out(amount_in, fwd[0], fwd[1])
    return amount_out(bought, rev[0], rev[1])


def test_usdc_to_btc_at_50k_no_spread() -> None:
    s2a, a2s = compute_price_pair(
        price_e18=BTC_E18,
        decimals_stable=USDC_DEC,
        decimals_asset=WBTC_DEC,
        spread_bps=0,
    )
    # 50_000 USDC = 50_000 * 10^6 raw = 5e10. At $50k/BTC, that's 1.0 BTC = 10^8 raw.
    got = amount_out(50_000 * 10**USDC_DEC, *s2a)
    assert got == 10**WBTC_DEC, f"expected 1 BTC raw (1e8), got {got}"
    # 1 BTC -> 50_000 USDC raw exact (no spread).
    back = amount_out(10**WBTC_DEC, *a2s)
    assert back == 50_000 * 10**USDC_DEC


def test_usdc_to_eth_at_3k_no_spread() -> None:
    s2a, _ = compute_price_pair(
        price_e18=ETH_E18,
        decimals_stable=USDC_DEC,
        decimals_asset=WETH_DEC,
        spread_bps=0,
    )
    # 3_000 USDC -> 1 ETH (10^18 raw)
    got = amount_out(3_000 * 10**USDC_DEC, *s2a)
    assert got == 10**WETH_DEC


def test_usdc_to_sol_at_150_no_spread() -> None:
    s2a, _ = compute_price_pair(
        price_e18=SOL_E18,
        decimals_stable=USDC_DEC,
        decimals_asset=WSOL_DEC,
        spread_bps=0,
    )
    # 150 USDC -> 1 SOL (10^9 raw)
    got = amount_out(150 * 10**USDC_DEC, *s2a)
    assert got == 10**WSOL_DEC


def test_default_spread_burns_round_trip() -> None:
    """Buy then sell at the default 5 bps each leg leaves ~10 bps gone."""
    s2a, a2s = compute_price_pair(
        price_e18=ETH_E18,
        decimals_stable=USDC_DEC,
        decimals_asset=WETH_DEC,
    )
    start = 10_000 * 10**USDC_DEC
    end = _round_trip(start, s2a, a2s)
    # Each leg: 9995/10000. Round trip: (9995/10000)^2 ≈ 0.999000 → 0.1% loss.
    # Pin the upper bound (no gain) and the lower bound (≤ 11 bps loss).
    assert end < start
    loss_bps = (start - end) * 10_000 // start
    assert 9 <= loss_bps <= 11, f"expected ~10 bps round-trip loss, got {loss_bps}"


def test_spread_zero_gives_no_loss_round_trip() -> None:
    """Pure mid pricing should round-trip exactly (modulo integer floor)."""
    s2a, a2s = compute_price_pair(
        price_e18=ETH_E18,
        decimals_stable=USDC_DEC,
        decimals_asset=WETH_DEC,
        spread_bps=0,
    )
    start = 10_000 * 10**USDC_DEC
    end = _round_trip(start, s2a, a2s)
    # Floor division can shave a few wei; expect equal or 1-token-ulp lower.
    assert 0 <= start - end <= 10


def test_decimals_in_equals_out() -> None:
    """Two 18-dec tokens at $1 each — 1:1 swap."""
    s2a, a2s = compute_price_pair(
        price_e18=10**18,
        decimals_stable=18,
        decimals_asset=18,
        spread_bps=0,
    )
    one_token = 10**18
    assert amount_out(one_token, *s2a) == one_token
    assert amount_out(one_token, *a2s) == one_token


def test_decimals_in_greater_than_out() -> None:
    """USDC (6) -> WBTC (8) is in<out; this case the reverse direction.
    Swap an 18-dec stable for a 6-dec asset (e.g. some hypothetical
    high-precision oracle of a low-precision token)."""
    s2a, _ = compute_price_pair(
        price_e18=10**18,  # parity stable<->asset
        decimals_stable=18,
        decimals_asset=6,
        spread_bps=0,
    )
    # 1 stable (10^18) -> 1 asset (10^6)
    assert amount_out(10**18, *s2a) == 10**6


def test_decimals_in_less_than_out() -> None:
    """USDC (6) -> WETH (18). 1 stable -> 1 asset at parity."""
    s2a, _ = compute_price_pair(
        price_e18=10**18,
        decimals_stable=6,
        decimals_asset=18,
        spread_bps=0,
    )
    assert amount_out(10**6, *s2a) == 10**18


def test_default_spread_constant_is_five_bps() -> None:
    assert DEFAULT_SPREAD_BPS == 5


@pytest.mark.parametrize("price", [0, -1])
def test_rejects_non_positive_price(price: int) -> None:
    with pytest.raises(ValueError):
        compute_price_pair(price_e18=price, decimals_stable=6, decimals_asset=18)


@pytest.mark.parametrize("d_stable,d_asset", [(-1, 18), (6, -1)])
def test_rejects_negative_decimals(d_stable: int, d_asset: int) -> None:
    with pytest.raises(ValueError):
        compute_price_pair(price_e18=10**18, decimals_stable=d_stable, decimals_asset=d_asset)


@pytest.mark.parametrize("bps", [-1, 10_000, 99_999])
def test_rejects_out_of_range_spread(bps: int) -> None:
    with pytest.raises(ValueError):
        compute_price_pair(
            price_e18=10**18,
            decimals_stable=6,
            decimals_asset=18,
            spread_bps=bps,
        )


def test_amount_out_rejects_zero_denom() -> None:
    with pytest.raises(ValueError):
        amount_out(10**6, 1, 0)
