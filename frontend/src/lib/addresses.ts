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
  // Legacy (Phase-1/2/3) base proxies — `active=false` post 2026-05-09
  // Phase-6 cutover. Retained on the type so historical defund queries
  // and `Upgraded`-event archeology still resolve. New consumers should
  // read the `phase6Vault*` fields below.
  readonly strategyVaultMomentum?: Address;
  readonly strategyVaultMeanReversion?: Address;
  readonly strategyVaultYieldRotation?: Address;
  // Phase-6 multi-asset vaults — currently active in StrategyRegistry.
  // Universe per class: mom/mr [USDC, WBTC, WETH, SOL]; yr [USDC] only.
  readonly phase6VaultMomentum?: Address;
  readonly phase6VaultMomentumVariant2?: Address;
  readonly phase6VaultMomentumVariant3?: Address;
  readonly phase6VaultMeanReversion?: Address;
  readonly phase6VaultMeanReversionVariant2?: Address;
  readonly phase6VaultMeanReversionVariant3?: Address;
  readonly phase6VaultYieldRotation?: Address;
  readonly phase6VaultYieldRotationVariant2?: Address;
  readonly phase6VaultYieldRotationVariant3?: Address;
  // Phase-6 multi-asset test universe (`DeployTestUniverse.s.sol`).
  readonly mWbtc?: Address;
  readonly mWeth?: Address;
  readonly mSol?: Address;
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

/**
 * Active strategy-vault base proxies, keyed by declared class. As of
 * the 2026-05-09 Phase-6 real-price cutover, the canonical addresses
 * are the `phase6Vault*` keys; the legacy `strategyVault*` proxies
 * have been deactivated in `StrategyRegistry`. Consumers that need
 * variants (V2/V3) should read them off `addressesForChainId()`
 * directly.
 */
export const STRATEGY_VAULTS_BY_CLASS = {
  momentum_v1: KITE.addresses.phase6VaultMomentum,
  mean_reversion_v1: KITE.addresses.phase6VaultMeanReversion,
  yield_rotation_v1: KITE.addresses.phase6VaultYieldRotation,
} as const;
