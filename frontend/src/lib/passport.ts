/**
 * Kite Passport / ERC-4337 onboarding primitives.
 *
 * `@gokite-network/auth` wraps `@particle-network/auth` to give us a
 * passkey/email/social login that mints an ERC-4337 smart account
 * owned by a Particle-MPC EOA. `gokite-aa-sdk` is the userOp client.
 *
 * Both libraries touch `window` / `navigator` / `localStorage` at
 * import time, so this module is dynamic-imported inside the
 * PassportProvider — never `await import()` it from a server
 * component. Type re-exports are safe (types are stripped at build
 * time).
 *
 * Helios.md §6.1 (UserVault custody), `docs/kite-passport-notes.md`
 * §"Pattern 1" (the four-call onboarding batch).
 */

import { type Hex } from "viem";

export type PassportEnv = {
  particleProjectId: string;
  particleClientKey: string;
  particleAppId: string;
  entryPointAddress: Hex;
  factoryAddress: Hex;
  rpcUrl: string;
  bundlerUrl: string;
  chainId: number;
  /**
   * Salt fed into `gokite-aa-sdk`'s CREATE2 derivation. Same EOA + same
   * salt = same AA, so bumping this rotates every Passport user onto a
   * brand-new AA address with a fresh paymaster sponsorship counter
   * (5/5). Use only when an AA is sponsorship-locked and the on-chain
   * state on the old address can be abandoned (capital still recoverable
   * via `UserVault.withdraw`). Default 2 matches the SDK's hardcoded
   * `generateSalt() = BigInt(2)`.
   */
  aaSalt: bigint;
};

export function readPassportEnv(): PassportEnv | null {
  const particleProjectId = process.env.NEXT_PUBLIC_PARTICLE_PROJECT_ID ?? "";
  const particleClientKey = process.env.NEXT_PUBLIC_PARTICLE_CLIENT_KEY ?? "";
  const particleAppId = process.env.NEXT_PUBLIC_PARTICLE_APP_ID ?? "";
  const entryPointAddress = (process.env.NEXT_PUBLIC_AA_ENTRYPOINT_ADDRESS ?? "") as Hex;
  const factoryAddress = (process.env.NEXT_PUBLIC_AA_FACTORY_ADDRESS ?? "") as Hex;
  const rpcUrl = process.env.NEXT_PUBLIC_KITE_RPC_URL ?? "https://rpc-testnet.gokite.ai";
  // gokite-aa-sdk requires a bundler URL (it throws "Bundler URL is
  // required" when omitted). The staging bundler is the canonical one
  // referenced in the SDK's example.js for kite_testnet.
  const bundlerUrl =
    process.env.NEXT_PUBLIC_AA_BUNDLER_URL ?? "https://bundler-service.staging.gokite.ai/rpc/";
  const chainId = Number(process.env.NEXT_PUBLIC_KITE_CHAIN_ID ?? "2368");
  const aaSalt = BigInt(process.env.NEXT_PUBLIC_AA_SALT ?? "2");
  if (
    !particleProjectId
    || !particleClientKey
    || !particleAppId
    || !entryPointAddress
    || !factoryAddress
  ) {
    return null;
  }
  return {
    particleProjectId,
    particleClientKey,
    particleAppId,
    entryPointAddress,
    factoryAddress,
    rpcUrl,
    bundlerUrl,
    chainId,
    aaSalt,
  };
}

export function isPassportEnabled(): boolean {
  // The dev flag must be explicit "1" / "true" — anything else (empty,
  // missing, "0") falls back to EIP-191 so the e2e harness against
  // anvil keeps working without Particle credentials.
  const flag = (process.env.NEXT_PUBLIC_USE_PASSPORT ?? "").toLowerCase();
  if (flag !== "1" && flag !== "true") return false;
  return readPassportEnv() !== null;
}

/**
 * Authentication mode included in `MetaStrategyPayload`. The server
 * uses this to decide whether to verify the EIP-191 signature
 * (`eip191`) or trust on-chain authorization at the EntryPoint
 * (`passport`). Both paths still enforce the (user, nonce) /
 * `valid_until` replay window.
 */
export type AuthMode = "passport" | "eip191";
