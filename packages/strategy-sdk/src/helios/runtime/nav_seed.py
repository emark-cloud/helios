"""Seed a strategy's `_available_capital_usd` and `_nav_usd` from
the on-chain balances held by its `StrategyVault`.

Why this exists: the live runtime never invoked `_set_capital` / `_set_nav`
on the strategy. Without that, `available_capital == 0` and
`nav_target_notional` returns 0, so even a fired signal sizes to 0 USD,
which the directional circuits now reject (Constraint 0: `amount_in > 0`).
The reference allocator deposits real capital into the vault via
`AllocatorVault.allocateToStrategy → StrategyVault.acceptDeposit`, but
that on-chain state was never reflected back into the Python strategy.

This helper bridges the gap by reading `IERC20.balanceOf(vault)` once
per bar and seeding `available_capital` (and, by default, `nav`) to the
base-asset balance scaled to a USD float (base asset is mUSDC at 18
decimals on Kite testnet, 6 on Base/Arb).

`available_capital` is spendable base cash and is *always* set here —
it is also the ceiling the witness builder clamps `amount_in` to. But
NAV is mark-to-market (cash + held non-base positions). A runtime that
has a live price source for the rest of the universe can pass
`set_nav=False` and own NAV itself, valuing each non-base holding at
the oracle price (see `read_erc20_balance`). Without that, a vault that
has done any non-base swaps reports its NAV as ~0 (only the drained
base leg is counted), which collapses `nav_target_notional` sizing and
posts a wrong on-chain `reportNAV`. Strategies with a single-asset
(base-only) footprint can keep the default `set_nav=True`.
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


def read_erc20_balance(
    *,
    w3: Any,
    token_address: str,
    holder_address: str,
) -> int:
    """Return the raw `IERC20(token).balanceOf(holder)` (native token
    units — caller scales by `10**decimals`). Returns 0 if any input is
    falsy so callers can short-circuit in dry-run mode. Used both for
    the base-asset cash seed and for valuing held non-base positions in
    a position-aware NAV.
    """
    if not (w3 and token_address and holder_address):
        return 0
    contract = w3.eth.contract(
        address=w3.to_checksum_address(token_address),
        abi=_ERC20_BALANCE_ABI,
    )
    return int(contract.functions.balanceOf(w3.to_checksum_address(holder_address)).call())


def read_base_asset_balance(
    *,
    w3: Any,
    base_asset_address: str,
    vault_address: str,
) -> int:
    """Back-compat alias: the vault's base-asset balance is just an
    ERC20 `balanceOf` like any other token."""
    return read_erc20_balance(w3=w3, token_address=base_asset_address, holder_address=vault_address)


def seed_strategy_capital(
    *,
    strategy: Any,
    w3: Any,
    base_asset_address: str,
    vault_address: str,
    base_asset_decimals: int = 18,
    set_nav: bool = True,
) -> float:
    """Read the vault's base-asset balance and seed `available_capital`
    (spendable cash) on the strategy. Returns that USD value (0.0 in
    dry-run mode).

    `nav` is also set to the same cash value when `set_nav=True` (the
    default — correct for a base-only footprint). A runtime that values
    held non-base positions itself must pass `set_nav=False` and call
    `strategy._set_nav(...)` with the mark-to-market total; otherwise a
    vault that has swapped its base leg into other assets would report
    NAV ≈ 0 and `nav_target_notional` would size every entry to ~0."""
    raw = read_base_asset_balance(
        w3=w3, base_asset_address=base_asset_address, vault_address=vault_address
    )
    usd = raw / (10**base_asset_decimals)
    strategy._set_capital(usd)
    if set_nav:
        strategy._set_nav(usd)
    # Keep the exact integer alongside the float so witness builders
    # can clamp `amount_in` to a value the vault can actually fund.
    # See `StrategyAgent._set_base_asset_balance_wei` for the why.
    if hasattr(strategy, "_set_base_asset_balance_wei"):
        strategy._set_base_asset_balance_wei(raw)
    return usd
