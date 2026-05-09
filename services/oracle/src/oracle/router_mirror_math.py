"""Pure decimal converter for the oracle->MockSwapRouter price mirror.

The oracle publishes asset prices as `price_e18 = USD_price * 10^18`.
`MockSwapRouter.exactInputSingle` does `amountOut = amountIn * num / denom`
in raw token units (each token's native decimals). For each
`(stable, asset)` pair we need to compute `(num, denom)` for both swap
directions so the router prices the leg correctly given that decimals
differ across assets (USDC=6, WBTC=8, WETH=18, SOL=9).

The math, derived once and pinned by tests:

  stable -> asset:
    amountOut_asset_raw = amountIn_stable_raw * 10^(18+dec_asset) /
                          (price_e18 * 10^dec_stable)
    => num   = 10^18 * 10^dec_asset
       denom = price_e18 * 10^dec_stable

  asset -> stable:
    amountOut_stable_raw = amountIn_asset_raw * price_e18 *
                           10^(dec_stable - 18 - dec_asset)
    => num   = price_e18 * 10^dec_stable
       denom = 10^18 * 10^dec_asset

A 5 bps spread (configurable) is applied per direction by scaling
`num` down by `(10000 - spread_bps) / 10000`. Pricing the sell leg
strictly worse than the mid keeps round-trip arbitrage off the
demo path without swamping signal P&L.

USDC is the implicit stable in v1; the converter is agnostic so any
stable can occupy that role if the oracle ever publishes a non-1.0
USD price for it (the price_e18 input would carry the deviation).
"""

from __future__ import annotations

DEFAULT_SPREAD_BPS = 5


def compute_price_pair(
    *,
    price_e18: int,
    decimals_stable: int,
    decimals_asset: int,
    spread_bps: int = DEFAULT_SPREAD_BPS,
) -> tuple[tuple[int, int], tuple[int, int]]:
    """Return both swap directions for a (stable, asset) pair.

    Output: ((stable_to_asset_num, denom), (asset_to_stable_num, denom)).

    Raises ValueError on inputs the math can't represent (price <= 0,
    decimals < 0, spread outside [0, 10_000]).
    """
    if price_e18 <= 0:
        raise ValueError("price_e18 must be > 0")
    if decimals_stable < 0 or decimals_asset < 0:
        raise ValueError("decimals must be >= 0")
    if not 0 <= spread_bps < 10_000:
        raise ValueError("spread_bps must be in [0, 10_000)")

    spread_num = 10_000 - spread_bps
    spread_denom = 10_000

    pow18 = 10**18
    pow_stable = 10**decimals_stable
    pow_asset = 10**decimals_asset

    # stable -> asset: amountOut = amountIn * (10^18 * 10^dec_asset) / (price_e18 * 10^dec_stable)
    s2a_num = pow18 * pow_asset * spread_num
    s2a_denom = price_e18 * pow_stable * spread_denom

    # asset -> stable: amountOut = amountIn * (price_e18 * 10^dec_stable) / (10^18 * 10^dec_asset)
    a2s_num = price_e18 * pow_stable * spread_num
    a2s_denom = pow18 * pow_asset * spread_denom

    return (s2a_num, s2a_denom), (a2s_num, a2s_denom)


def amount_out(amount_in: int, num: int, denom: int) -> int:
    """Mirror `MockSwapRouter.exactInputSingle`'s integer math so tests
    can compare apples to apples without spinning up the EVM."""
    if denom == 0:
        raise ValueError("denom must be > 0")
    return (amount_in * num) // denom


__all__ = ["DEFAULT_SPREAD_BPS", "amount_out", "compute_price_pair"]
