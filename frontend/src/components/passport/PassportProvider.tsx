/**
 * PassportProvider — wraps the app in a Kite Passport context.
 *
 * Mounted *inside* `<WagmiProvider>` so the wagmi hooks remain
 * available for operator/dev paths (the e2e harness signs with anvil
 * keys, not Passport). The Passport SDK is lazy-imported on first
 * `login()` call to keep `@particle-network/auth`'s `window` /
 * `navigator` accesses out of the SSR critical path.
 *
 * Pattern 1 of `docs/kite-passport-notes.md`: passkey login → AA
 * smart-account address → batched userOp via `gokite-aa-sdk`.
 */

"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { isPassportEnabled, readPassportEnv, type AuthMode } from "@/lib/passport";

// Note: the `process.stdout/stderr.isTTY` shim that Particle's pino
// logger needs during passkey signing is installed by the synchronous
// `<script src="/process-tty-polyfill.js" />` in `app/layout.tsx`.
// Doing it from `<head>` instead of from this module guarantees the
// global exists before webpack's lazy chunk for `@particle-network/auth`
// starts initializing — an in-module polyfill races that import.

type SignFn = (_userOpHash: string) => Promise<string>;

export type PassportSession = {
  aaAddress: `0x${string}`;
  eoaAddress: `0x${string}`;
};

type PassportAuth = {
  isLogin(): boolean;
  login(_options?: object): Promise<unknown>;
  logout(_hideLoading?: boolean): Promise<void>;
  getUserInfo(): { wallets?: Array<{ public_address: string }> } | null;
  sign(_method: string, _message: string): Promise<string>;
};

type PassportSdkBundle = {
  // Loose-typed handles to keep this provider free of build-time
  // dependencies on `@gokite-network/auth` types — tests run without
  // the package and any signature drift between minor releases would
  // otherwise break the build.
  network: unknown;
  particleAuth: PassportAuth;
  smartAccount: { getAddress(): Promise<string> };
  aaSdk: {
    sendUserOperationAndWait(
      _owner: string,
      _request: { targets: string[]; values?: bigint[]; callDatas: string[] },
      _signFn: SignFn,
      _salt?: bigint,
      _paymasterAddress?: string,
      _pollingOptions?: { interval?: number; timeout?: number; maxRetries?: number },
    ): Promise<{
      userOpHash: string;
      status: { status: string; transactionHash?: string; reason?: string };
    }>;
    sendUserOperationWithPayment(
      _owner: string,
      _request: { targets: string[]; values?: bigint[]; callDatas: string[] },
      _baseUserOp: object,
      _tokenAddress: string,
      _signFn: SignFn,
      _salt?: bigint,
      _pollingOptions?: { interval?: number; timeout?: number; maxRetries?: number },
    ): Promise<{
      userOpHash: string;
      status: { status: string; transactionHash?: string; reason?: string };
    }>;
    getAccountAddress(_owner: string, _salt?: bigint): string;
    estimateUserOperation(
      _owner: string,
      _request: { targets: string[]; values?: bigint[]; callDatas: string[] },
    ): Promise<{
      sponsorshipAvailable: boolean;
      remainingSponsorships: number;
      paymasterAddress?: string;
      supportedTokens: Array<{
        tokenAddress: string;
        tokenSymbol?: string;
        tokenDecimals?: number;
        estimatedCost: string;
        formattedCost?: string;
      }>;
      userOp: object;
      gasEstimate?: object;
      totalCostKITE?: string;
      totalCostKITEFormatted?: string;
    }>;
  };
  signFn: SignFn;
};

type PassportContextValue = {
  enabled: boolean;
  ready: boolean;
  session: PassportSession | null;
  bundle: PassportSdkBundle | null;
  login(): Promise<PassportSession>;
  logout(): Promise<void>;
  authMode: AuthMode;
};

const PassportContext = createContext<PassportContextValue | null>(null);

export function usePassport(): PassportContextValue {
  const ctx = useContext(PassportContext);
  if (ctx === null) {
    // Outside a PassportProvider: behave as "disabled". Saves dashboard
    // surfaces from having to know whether the provider mounted.
    return DISABLED_VALUE;
  }
  return ctx;
}

const DISABLED_VALUE: PassportContextValue = {
  enabled: false,
  ready: true,
  session: null,
  bundle: null,
  login: async () => {
    throw new Error("Passport is not enabled — set NEXT_PUBLIC_USE_PASSPORT=1.");
  },
  logout: async () => {
    /* no-op */
  },
  authMode: "eip191",
};

export function PassportProvider({ children }: { children: ReactNode }): JSX.Element {
  const enabled = isPassportEnabled();
  const env = readPassportEnv();

  const [session, setSession] = useState<PassportSession | null>(null);
  const bundleRef = useRef<PassportSdkBundle | null>(null);

  const ensureBundle = useCallback(async (): Promise<PassportSdkBundle> => {
    if (bundleRef.current !== null) return bundleRef.current;
    if (env === null) {
      throw new Error(
        "Passport env incomplete — populate NEXT_PUBLIC_PARTICLE_* and NEXT_PUBLIC_AA_*.",
      );
    }
    // Lazy import keeps `@particle-network/auth`'s top-level
    // `window` / IndexedDB access off the SSR critical path. Both
    // packages are listed as runtime deps in package.json.
    const [particleMod, gokiteAuthMod, aaSdkMod] = await Promise.all([
      import("@particle-network/auth"),
      import("@gokite-network/auth"),
      import("gokite-aa-sdk"),
    ]);

    const ParticleNetworkCtor = (
      particleMod as { ParticleNetwork: new (_cfg: object) => { auth: unknown } }
    ).ParticleNetwork;
    const particle = new ParticleNetworkCtor({
      projectId: env.particleProjectId,
      clientKey: env.particleClientKey,
      appId: env.particleAppId,
      chainId: env.chainId,
      // Must match the key `@gokite-network/auth` registers on
      // `ParticleChains`: `gokiteTestnet.name.split(" ")[0].toLowerCase()`
      // = "gokite". Passing "Kite" makes Particle look up "kite-2368"
      // which is unregistered, so the userOp signer throws EIP-1193
      // 4201 ("The Provider does not support the chain") mid-passkey.
      chainName: "Gokite",
    });
    const particleAuth = particle.auth as PassportAuth;

    const SmartAccountCtor = (gokiteAuthMod as { SmartAccount: new (..._args: unknown[]) => unknown })
      .SmartAccount;
    const gokiteTestnetChain = (gokiteAuthMod as { gokiteTestnet: unknown }).gokiteTestnet;
    const NetworkCtor = (
      gokiteAuthMod as { default?: new (..._args: unknown[]) => unknown }
    ).default!;
    const smartAccount = new SmartAccountCtor(particleAuth, gokiteTestnetChain, {
      entryPointAddress: env.entryPointAddress,
      smartAccountFactoryAddress: env.factoryAddress,
      secretKey: env.particleClientKey,
    }) as PassportSdkBundle["smartAccount"];
    const network = new NetworkCtor(smartAccount, particleAuth);

    const AaSdkCtor = (aaSdkMod as { GokiteAASDK: new (..._args: unknown[]) => unknown }).GokiteAASDK;
    // gokite-aa-sdk's NETWORKS map keys are `kite_testnet` /
    // `kite_mainnet` (underscore). Passing "kite-testnet" hits the
    // `throw new Error("Unsupported network: …")` branch in
    // gokite-aa-sdk@1.0.15/dist/gokite-aa-sdk.js:183.
    //
    // Third arg is the bundler URL — the constructor throws "Bundler
    // URL is required" when it's omitted. Default points at the
    // canonical staging bundler from the SDK's own example.js.
    const aaSdk = new AaSdkCtor(
      "kite_testnet",
      env.rpcUrl,
      env.bundlerUrl,
    ) as PassportSdkBundle["aaSdk"];

    // The userOp signer surfaces the userOp hash to Particle for the
    // user's passkey to sign — Particle returns a 0x-prefixed signature
    // on the EntryPoint's `getUserOpHash` digest. Single passkey
    // prompt covers the whole batched userOp.
    const signFn: SignFn = async (userOpHash: string) => {
      const sig = await (
        particleAuth as { sign: (_method: string, _message: string) => Promise<string> }
      ).sign("personal_sign", userOpHash as `0x${string}`);
      return sig;
    };

    const bundle: PassportSdkBundle = {
      network,
      particleAuth,
      smartAccount,
      aaSdk,
      signFn,
    };
    bundleRef.current = bundle;
    return bundle;
  }, [env]);

  const login = useCallback(async (): Promise<PassportSession> => {
    if (!enabled) {
      throw new Error("Passport is not enabled — set NEXT_PUBLIC_USE_PASSPORT=1.");
    }
    const bundle = await ensureBundle();
    // Drive the Particle passkey modal directly. `GokiteNetwork.login()`
    // in @gokite-network/auth@<=current has an inverted check
    // (`if (!isLogin()) return getUserInfo()`) — for first-time users
    // it short-circuits to a stale userInfo without ever opening the
    // modal, which then trips `SmartAccount Error: EOA address is empty`
    // on `getAddress()`. Calling `particleAuth.login()` ourselves
    // bypasses that bug; we still keep `bundle.network` around for the
    // logout / signin RPC paths.
    if (!bundle.particleAuth.isLogin()) {
      await bundle.particleAuth.login({});
    }
    // Derive the AA via gokite-aa-sdk's getAccountAddress(owner=eoa,
    // salt=2). MUST match what `aaSdk.estimateUserOperation` /
    // `sendUserOperationWithPayment` compute for the userOp `sender`,
    // since the SDK hardcodes salt=2 and treats the first arg as the
    // owner EOA. The earlier path used `bundle.smartAccount.getAddress()`
    // from `@gokite-network/auth`, which derives a different address
    // (salt = keccak256(particleClientKey)) — the userOp would deploy
    // an account at the SDK address while we displayed/funded the
    // gokite-auth address, and validateUserOp failed on-chain.
    const eoaInfo = bundle.particleAuth.getUserInfo();
    const eoaAddress = (eoaInfo?.wallets?.[0]?.public_address ?? "") as `0x${string}`;
    if (!eoaAddress) {
      throw new Error("Particle login returned no EOA wallet — cannot derive AA address.");
    }
    const aaAddress = bundle.aaSdk.getAccountAddress(eoaAddress) as `0x${string}`;
    const next: PassportSession = { aaAddress, eoaAddress };
    setSession(next);
    return next;
  }, [enabled, ensureBundle]);

  const logout = useCallback(async (): Promise<void> => {
    if (bundleRef.current === null) {
      setSession(null);
      return;
    }
    await (
      bundleRef.current.network as { logout: () => Promise<void> }
    ).logout();
    setSession(null);
  }, []);

  const value = useMemo<PassportContextValue>(
    () => ({
      enabled,
      ready: true,
      session,
      bundle: bundleRef.current,
      login,
      logout,
      authMode: enabled ? "passport" : "eip191",
    }),
    [enabled, session, login, logout],
  );

  return <PassportContext.Provider value={value}>{children}</PassportContext.Provider>;
}
