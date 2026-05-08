"""Aave V3 Pool adapter for yield_rotation_v1.

Phase-5 yield-rotation runs against the canonical Aave V3 `Pool`
deployment on Arbitrum Sepolia (`0xBfC91D59fdAA134A4ED45f7B584cAf96D7792Eff`).
The strategy decides between supply tokens (e.g. USDC vs USDT on the
same Pool) and emits a rotation when the realized APY delta exceeds
`signal_threshold_bps + bridging_cost_bps`.

This module exposes the narrow surface the executor needs:

  * `build_aave_supply_calldata(...)` — encodes
    `Pool.supply(asset, amount, onBehalfOf, referralCode)`.
  * `build_aave_withdraw_calldata(...)` — encodes
    `Pool.withdraw(asset, amount, to)`.
  * `aave_apy_view(...)` — reads `Pool.getReserveData(asset)` and
    returns the current liquidity rate (in the Aave-V3 ray-fixed
    `1e27` convention) so the runtime can compare cross-protocol
    rates without going through the oracle for an APY-only signal.

The mock-fallback `MockYieldVault` shipped with WS2 mirrors the same
calldata shape (and the `currentLiquidityRate(asset)` accessor) so
the executor branches on `venue_mode` only at the address level.

phase5-plan.md §WS4.
"""

from __future__ import annotations

from typing import Any

from eth_utils.crypto import keccak

# `function supply(address,uint256,address,uint16)`
_SUPPLY_SELECTOR = keccak(b"supply(address,uint256,address,uint16)")[:4]

# `function withdraw(address,uint256,address)` — V3 returns uint256.
_WITHDRAW_SELECTOR = keccak(b"withdraw(address,uint256,address)")[:4]

# `function currentLiquidityRate(address)` — present on MockYieldVault and
# accepted as a shorthand on the real Pool when callers only need the
# liquidity-rate slice. The full `getReserveData` returns a struct that
# requires a Solidity-shaped decoder; the SDK's APY read uses
# `currentLiquidityRate` against MockYieldVault and the dedicated
# data-provider on the real venue (`AaveProtocolDataProvider`).
_CURRENT_LIQUIDITY_RATE_SELECTOR = keccak(b"currentLiquidityRate(address)")[:4]

# Aave V3 ray fixed-point — 1.0 == 1e27. APY in basis points converts
# back as `apy_bps = rate_ray * 10_000 / RAY`.
RAY = 10**27
SECONDS_PER_YEAR = 365 * 24 * 60 * 60


def build_aave_supply_calldata(
    *,
    asset: str,
    amount: int,
    on_behalf_of: str,
    referral_code: int = 0,
) -> bytes:
    """Encode `Pool.supply(asset, amount, onBehalfOf, referralCode)`.

    Four 32-byte words behind the V3 selector. `referralCode` is a
    uint16 in the ABI but ABI-encoding right-pads it to a full word.
    """
    if amount < 0:
        raise ValueError("amount must be non-negative")
    if not 0 <= referral_code < 2**16:
        raise ValueError("referral_code must fit in uint16")
    words = [
        _addr_word(asset),
        int(amount).to_bytes(32, "big"),
        _addr_word(on_behalf_of),
        int(referral_code).to_bytes(32, "big"),
    ]
    return _SUPPLY_SELECTOR + b"".join(words)


def build_aave_withdraw_calldata(
    *,
    asset: str,
    amount: int,
    to: str,
) -> bytes:
    """Encode `Pool.withdraw(asset, amount, to)`.

    `amount = type(uint256).max` saturates to the full position —
    the canonical Aave V3 idiom for a full exit. Callers pass that
    value directly when rotating out of a market entirely.
    """
    if amount < 0:
        raise ValueError("amount must be non-negative")
    words = [
        _addr_word(asset),
        int(amount).to_bytes(32, "big"),
        _addr_word(to),
    ]
    return _WITHDRAW_SELECTOR + b"".join(words)


def build_current_liquidity_rate_calldata(*, asset: str) -> bytes:
    """Encode `currentLiquidityRate(asset)` — the MockYieldVault APY
    accessor. The real Aave Pool exposes the same field via
    `getReserveData` but unpacking that struct from Python is heavy;
    use the dedicated `AaveProtocolDataProvider` for the real venue
    (out of scope for v1 — `aave_apy_view` covers the mock path)."""
    return _CURRENT_LIQUIDITY_RATE_SELECTOR + _addr_word(asset)


def aave_apy_view(*, w3: Any, pool_address: str, asset: str) -> int:
    """Read `currentLiquidityRate(asset)` and return the rate in
    Aave's ray-fixed 1e27 convention. Convert to bps with
    `rate_ray * 10_000 / RAY`. Live-only — callers in dry-run mode
    fall back to the oracle yield feed."""
    call_data = build_current_liquidity_rate_calldata(asset=asset)
    raw = w3.eth.call({"to": pool_address, "data": "0x" + call_data.hex()})
    if not raw:
        return 0
    return int.from_bytes(bytes(raw[:32]), "big")


def ray_to_apy_bps(rate_ray: int) -> int:
    """Convert a ray-fixed liquidity rate into integer basis points.
    Aave V3 quotes the rate per-second, but `currentLiquidityRate`
    is annualized in the ray; the SDK + MockYieldVault keep the
    annual convention so this is a simple scale."""
    return (rate_ray * 10_000) // RAY


def _addr_word(addr: str) -> bytes:
    """Pad a 0x-prefixed address into a 32-byte big-endian word."""
    if not addr.startswith(("0x", "0X")):
        # Symbol fallbacks aren't allowed for Aave — the real Pool
        # rejects unknown reserves and we'd rather fail loudly than
        # silently mis-encode a hashed symbol as an address.
        raise ValueError(f"asset must be a 0x-prefixed address, got: {addr!r}")
    raw = bytes.fromhex(addr[2:].rjust(40, "0"))
    return b"\x00" * 12 + raw
