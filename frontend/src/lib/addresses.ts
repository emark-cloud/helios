/**
 * Per-chain deployed addresses. Source of truth lives at
 * `contracts/deployments/<chain>.json`, written by the per-chain deploy
 * scripts. Frontend reads the JSON directly (Next.js `resolveJsonModule`)
 * — no hardcoded addresses elsewhere per CLAUDE.md.
 *
 * Three chains are loaded post-CXR-3 (2026-05-13): the canonical Kite
 * testnet + the Base-Sepolia spot venue (mom + mr against Uniswap V3) +
 * the Arbitrum-Sepolia yield venue (yr against an Aave-V3-shaped pool).
 * `@helios/contracts-abi/addresses` exports a typed shape too, but its
 * ADDRESSES map is populated by a separate generate step; importing the
 * JSONs directly keeps the frontend in sync with whatever the contracts
 * package shipped last broadcast.
 */

import type { Address } from "viem";

import kiteTestnet from "../../../contracts/deployments/kite-testnet.json";
import baseSepolia from "../../../contracts/deployments/base-sepolia.json";
import arbitrumSepolia from "../../../contracts/deployments/arbitrum-sepolia.json";

import { chainName, formatAddress, formatStrategyClass } from "./format";

export type ChainKey =
  | "kite-testnet"
  | "base-sepolia"
  | "arbitrum-sepolia"
  | "anvil";

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
  // CXR (2026-05-13) — cross-chain venue routing per §12.1.
  // LayerZero V2 OApp; same address on Kite + Base + Arb by deployer
  // nonce-coincidence on a fresh EOA.
  readonly heliosOApp?: Address;
  // Base-Sepolia spot vaults (Uniswap V3 SwapRouter02).
  readonly phase6VaultMomentumBase?: Address;
  readonly phase6VaultMeanReversionBase?: Address;
  // Arbitrum-Sepolia yield vault (Aave-V3-shaped MockYieldVault until the
  // admin-gated FiatToken USDC faucet opens up; one-line `allowedRouter`
  // flip swaps it to the real Aave V3 Pool).
  readonly phase6VaultYieldRotationArb?: Address;
  readonly aavePool?: Address;
  readonly mockYieldVault?: Address;
};

type DeploymentFile = {
  readonly chainId: number;
  readonly addresses: HeliosAddresses;
};

const KITE: DeploymentFile = kiteTestnet as DeploymentFile;
const BASE: DeploymentFile = baseSepolia as DeploymentFile;
const ARB: DeploymentFile = arbitrumSepolia as DeploymentFile;

export const CHAIN_ADDRESSES: Record<ChainKey, HeliosAddresses> = {
  "kite-testnet": KITE.addresses,
  "base-sepolia": BASE.addresses,
  "arbitrum-sepolia": ARB.addresses,
  // Anvil deployments are written at scenario boot; empty map keeps
  // typecheck happy when the file isn't present.
  anvil: {},
};

export const CHAIN_IDS: Record<ChainKey, number> = {
  "kite-testnet": KITE.chainId,
  "base-sepolia": BASE.chainId,
  "arbitrum-sepolia": ARB.chainId,
  anvil: 31_337,
};

export function addressesForChainId(chainId: number): HeliosAddresses {
  if (chainId === KITE.chainId) return KITE.addresses;
  if (chainId === BASE.chainId) return BASE.addresses;
  if (chainId === ARB.chainId) return ARB.addresses;
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

/**
 * Human-readable name per deployed strategy-vault proxy. Built once at
 * module load from the deployments JSONs. Unknown addresses fall back
 * to `formatAddress` so the UI is still legible for strategies that
 * pre-date or post-date this map.
 */
const STRATEGY_LABELS: Readonly<Record<string, string>> = (() => {
  const out: Record<string, string> = {};
  const add = (addr: Address | undefined, label: string): void => {
    if (addr) out[addr.toLowerCase()] = label;
  };

  const k = KITE.addresses;
  add(k.phase6VaultMomentum, "Momentum · Kite #1");
  add(k.phase6VaultMomentumVariant2, "Momentum · Kite #2");
  add(k.phase6VaultMomentumVariant3, "Momentum · Kite #3");
  add(k.phase6VaultMeanReversion, "Mean reversion · Kite #1");
  add(k.phase6VaultMeanReversionVariant2, "Mean reversion · Kite #2");
  add(k.phase6VaultMeanReversionVariant3, "Mean reversion · Kite #3");
  add(k.phase6VaultYieldRotation, "Yield rotation · Kite #1");
  add(k.phase6VaultYieldRotationVariant2, "Yield rotation · Kite #2");
  add(k.phase6VaultYieldRotationVariant3, "Yield rotation · Kite #3");
  // Pre-Phase-6 legacy proxies — kept for historical defund/audit views.
  add(k.strategyVaultMomentum, "Momentum · Kite (legacy)");
  add(k.strategyVaultMeanReversion, "Mean reversion · Kite (legacy)");
  add(k.strategyVaultYieldRotation, "Yield rotation · Kite (legacy)");

  const b = BASE.addresses;
  add(b.phase6VaultMomentumBase, "Momentum · Base");
  add(b.phase6VaultMeanReversionBase, "Mean reversion · Base");

  const a = ARB.addresses;
  add(a.phase6VaultYieldRotationArb, "Yield rotation · Arbitrum");

  return out;
})();

export function strategyLabelFor(id: string): string | null {
  if (!id) return null;
  return STRATEGY_LABELS[id.toLowerCase()] ?? null;
}

/**
 * Friendly strategy name. Resolution order:
 *  1. Exact address → deployment label ("Momentum · Kite #1").
 *  2. Otherwise a class+chain name derived from `declaredClass`
 *     ("Mean reversion · Kite") — covers superseded predecessor vaults
 *     and NAV-retained legacy vaults that the subgraph still returns
 *     active but that aren't in the current deployments JSON.
 *  3. Truncated hex, only when the declared class is also unknown
 *     (phantom / non-canonical test registrations).
 */
export function formatStrategyName(
  id: string,
  meta?: { declaredClass?: string; chainId?: number },
): string {
  const exact = strategyLabelFor(id);
  if (exact) return exact;

  if (meta?.declaredClass) {
    const cls = formatStrategyClass(meta.declaredClass);
    // formatStrategyClass returns a truncated 0x… hash for unknown
    // classes; only treat it as a name when it actually resolved.
    if (cls && !cls.startsWith("0x")) {
      const chain = meta.chainId != null ? chainName(meta.chainId) : null;
      return chain && chain !== "Unknown" ? `${cls} · ${chain}` : cls;
    }
  }
  return formatAddress(id);
}

// ── Token metadata ──────────────────────────────────────────────────
//
// Subgraph Trade.amountIn / minAmountOut are raw integers in the
// token's own decimals. The Phase-6 multi-asset universe mixes
// decimals (mUSDC 18-dec on Kite / 6-dec on Base+Arb, mWBTC 8,
// mWETH 18, mSOL 9), so a single `/1e6` is wrong for almost
// everything. Resolve per (chainId, address).

type TokenMeta = { symbol: string; decimals: number; isUsd: boolean };

// OP-Stack WETH9 predeploy (Base-Sepolia spot universe — see CLAUDE.md
// §12.1). Not in the deployments JSON because it's a chain predeploy.
const BASE_WETH9 = "0x4200000000000000000000000000000000000006";

const TOKEN_META: Readonly<Record<string, TokenMeta>> = (() => {
  const out: Record<string, TokenMeta> = {};
  const put = (chainId: number, addr: string | undefined, m: TokenMeta): void => {
    if (addr) out[`${chainId}:${addr.toLowerCase()}`] = m;
  };

  const k = KITE.addresses;
  put(KITE.chainId, k.usdc, { symbol: "mUSDC", decimals: 18, isUsd: true });
  put(KITE.chainId, k.mWbtc, { symbol: "mWBTC", decimals: 8, isUsd: false });
  put(KITE.chainId, k.mWeth, { symbol: "mWETH", decimals: 18, isUsd: false });
  put(KITE.chainId, k.mSol, { symbol: "mSOL", decimals: 9, isUsd: false });

  const b = BASE.addresses;
  put(BASE.chainId, b.usdc, { symbol: "mUSDC", decimals: 6, isUsd: true });
  put(BASE.chainId, BASE_WETH9, { symbol: "WETH", decimals: 18, isUsd: false });

  const a = ARB.addresses;
  put(ARB.chainId, a.usdc, { symbol: "mUSDC", decimals: 6, isUsd: true });

  return out;
})();

export function tokenMetaFor(asset: string, chainId: number): TokenMeta | null {
  if (!asset) return null;
  return TOKEN_META[`${chainId}:${asset.toLowerCase()}`] ?? null;
}

/** Short token symbol for `asset` on `chainId`, else the truncated address. */
export function formatAssetSymbol(asset: string, chainId: number): string {
  return tokenMetaFor(asset, chainId)?.symbol ?? formatAddress(asset);
}

/**
 * Decode a raw subgraph token amount into a display quantity using the
 * token's true decimals. Returns null for tokens we don't know — the
 * caller renders "—" rather than guessing a scale (the old heuristic
 * mis-scaled every 18-dec value to "$0").
 */
export function decodeTokenAmount(
  raw: string,
  asset: string,
  chainId: number,
): { amount: number; symbol: string; isUsd: boolean } | null {
  const meta = tokenMetaFor(asset, chainId);
  if (!meta) return null;
  let big: bigint;
  try {
    big = BigInt(raw);
  } catch {
    return null;
  }
  const scale = 10n ** BigInt(meta.decimals);
  const whole = Number(big / scale);
  const frac = Number(big % scale) / Number(scale);
  return { amount: whole + frac, symbol: meta.symbol, isUsd: meta.isUsd };
}
