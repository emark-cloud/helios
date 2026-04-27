/**
 * Per-chain deployed addresses. Source of truth lives at
 * `contracts/deployments/<chain>.json`, written by `DeployPhase1.s.sol`.
 * Frontend reads the JSON directly (Next.js `resolveJsonModule`) — no
 * hardcoded addresses elsewhere per CLAUDE.md.
 *
 * `@helios/contracts-abi/addresses` exports a typed shape too, but its
 * ADDRESSES map is populated by a separate generate step. Until that
 * pipeline runs after every deploy, importing the JSON directly keeps
 * the frontend in sync with whatever the contracts package shipped.
 */

import type { Address } from "viem";

import kiteTestnet from "../../../contracts/deployments/kite-testnet.json";

export type ChainKey = "kite-testnet" | "anvil";

export type HeliosAddresses = {
  readonly usdc?: Address;
  readonly swapRouter?: Address;
  readonly reputationAnchor?: Address;
  readonly strategyRegistry?: Address;
  readonly allocatorRegistry?: Address;
  readonly tradeAttestationVerifier?: Address;
  readonly momentumVerifier?: Address;
  readonly meanReversionVerifier?: Address;
  readonly yieldRotationVerifier?: Address;
  readonly userVault?: Address;
  readonly allocatorVault?: Address;
  readonly strategyVaultMomentum?: Address;
  readonly strategyVaultMeanReversion?: Address;
  readonly strategyVaultYieldRotation?: Address;
};

type DeploymentFile = {
  readonly chainId: number;
  readonly addresses: HeliosAddresses;
};

const KITE: DeploymentFile = kiteTestnet as DeploymentFile;

export const CHAIN_ADDRESSES: Record<ChainKey, HeliosAddresses> = {
  "kite-testnet": KITE.addresses,
  // Anvil deployments are written at scenario boot; empty map keeps
  // typecheck happy when the file isn't present.
  anvil: {},
};

export const CHAIN_IDS: Record<ChainKey, number> = {
  "kite-testnet": KITE.chainId,
  anvil: 31_337,
};

export function addressesForChainId(chainId: number): HeliosAddresses {
  if (chainId === KITE.chainId) return KITE.addresses;
  if (chainId === 31_337) return CHAIN_ADDRESSES.anvil;
  return {};
}

/** The Phase 1 strategy vault addresses, ordered by class. */
export const STRATEGY_VAULTS_BY_CLASS = {
  momentum_v1: KITE.addresses.strategyVaultMomentum,
  mean_reversion_v1: KITE.addresses.strategyVaultMeanReversion,
  yield_rotation_v1: KITE.addresses.strategyVaultYieldRotation,
} as const;
