"""Seed a strategy's `_available_capital_usd` and `_nav_usd` from
the on-chain base-asset balance held by its `StrategyVault`.

Why this exists: the live runtime never invoked `_set_capital` / `_set_nav`
on the strategy. Without that, `available_capital == 0` and
`nav_target_notional` returns 0, so even a fired signal sizes to 0 USD,
which the directional circuits now reject (Constraint 0: `amount_in > 0`).
The reference allocator deposits real capital into the vault via
`AllocatorVault.allocateToStrategy → StrategyVault.acceptDeposit`, but
that on-chain state was never reflected back into the Python strategy.

This helper bridges the gap by reading `IERC20.balanceOf(vault)` once
per bar and seeding both `available_capital` and `nav` to that value
(scaled to USD float — base asset is mUSDC at 18 decimals on Kite
testnet). For Phase 6 demos this is exact when no positions are open;
once trades fire, the strategy's internal position-tracking augments
the cash floor. Phase 7 hardening will read per-asset balances + the
live oracle root to compute a position-aware NAV.
"""

from __future__ import annotations

from typing import Any

# Minimal ERC20 ABI — balanceOf(address) → uint256. No need to pull
# in OZ's full ABI; we only ever call this one function from the seed.
_ERC20_BALANCE_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
]


def read_base_asset_balance(
    *,
    w3: Any,
    base_asset_address: str,
    vault_address: str,
) -> int:
    """Return the raw (decimal-aware) ERC20 balance the vault holds of
    its base asset. Returns 0 if any input is falsy — callers can use
    that branch to short-circuit when running in dry-run mode.
    """
    if not (w3 and base_asset_address and vault_address):
        return 0
    contract = w3.eth.contract(
        address=w3.to_checksum_address(base_asset_address),
        abi=_ERC20_BALANCE_ABI,
    )
    return int(contract.functions.balanceOf(w3.to_checksum_address(vault_address)).call())


def seed_strategy_capital(
    *,
    strategy: Any,
    w3: Any,
    base_asset_address: str,
    vault_address: str,
    base_asset_decimals: int = 18,
) -> float:
    """Read the vault's base-asset balance and seed both
    `available_capital` and `nav` on the strategy. Returns the seeded
    USD value (0.0 in dry-run mode)."""
    raw = read_base_asset_balance(
        w3=w3, base_asset_address=base_asset_address, vault_address=vault_address
    )
    usd = raw / (10**base_asset_decimals)
    strategy._set_capital(usd)
    strategy._set_nav(usd)
    return usd
