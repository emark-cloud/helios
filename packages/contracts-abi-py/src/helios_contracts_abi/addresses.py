"""Per-chain deployed Helios contract addresses.

Populated by the generator after each deploy. Services read from this module
rather than hardcoding addresses, so redeploys only require regeneration.
"""

from typing import Literal, TypedDict

ChainName = Literal["kite-testnet", "base-sepolia", "arbitrum-sepolia", "anvil"]


class HeliosAddresses(TypedDict, total=False):
    helios: str
    userVault: str
    allocatorVault: str
    strategyRegistry: str
    allocatorRegistry: str
    reputationAnchor: str
    tradeAttestationVerifier: str
    heliosOApp: str


CHAIN_IDS: dict[ChainName, int] = {
    "kite-testnet": 2368,
    "base-sepolia": 84_532,
    "arbitrum-sepolia": 421_614,
    "anvil": 31_337,
}

# Phase 0 ships this empty. Populated by deploy scripts + `pnpm build`.
ADDRESSES: dict[ChainName, HeliosAddresses] = {
    "kite-testnet": {},
    "base-sepolia": {},
    "arbitrum-sepolia": {},
    "anvil": {},
}
