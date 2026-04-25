// Per-chain deployed contract addresses, populated by deploy scripts.
// Services and frontend read this rather than hardcoding addresses.
//
// The JSON under contracts/deployments/ is the source of truth; these
// exports merely shape it into a typed object. Regenerate after each deploy.

import type { Address } from "./types.js";

export type ChainName = "kite-testnet" | "base-sepolia" | "arbitrum-sepolia" | "anvil";

export type HeliosAddresses = {
  readonly helios?: Address;
  readonly userVault?: Address;
  readonly allocatorVault?: Address;
  readonly strategyRegistry?: Address;
  readonly allocatorRegistry?: Address;
  readonly reputationAnchor?: Address;
  readonly tradeAttestationVerifier?: Address;
  readonly heliosOApp?: Address;
};

export const CHAIN_IDS: Record<ChainName, number> = {
  "kite-testnet": 2368,
  "base-sepolia": 84_532,
  "arbitrum-sepolia": 421_614,
  "anvil": 31_337,
};

// Populated by `pnpm --filter contracts-abi build` after each deploy.
// The script reads contracts/deployments/*.json and emits this object.
// Phase 0 leaves it empty.
export const ADDRESSES: Record<ChainName, HeliosAddresses> = {
  "kite-testnet": {},
  "base-sepolia": {},
  "arbitrum-sepolia": {},
  "anvil": {},
};
