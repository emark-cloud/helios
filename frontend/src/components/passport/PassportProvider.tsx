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

// Webpack 5's browser shim for `process` exposes only `env`, but
// Particle's bundled pino logger reads `process.stdout.isTTY` /
// `process.stderr.isTTY` — that throws "Cannot read properties of
// undefined (reading 'isTTY')" exactly when `particleAuth.sign(...)`
// fires the passkey prompt. Patch the shim once at module load so
// the SDK's logger short-circuits to non-TTY output instead of
// crashing the userOp signing flow. Browser-only; SSR has real
// process.stdout already.
type StdShim = { isTTY: boolean };
type ProcessShim = { env: Record<string, string>; stdout?: StdShim; stderr?: StdShim };
if (typeof window !== "undefined") {
  const root = globalThis as { process?: ProcessShim };
  const proc: ProcessShim = root.process ?? (root.process = { env: {} });
  if (!proc.stdout) proc.stdout = { isTTY: false };
  if (!proc.stderr) proc.stderr = { isTTY: false };
}

type SignFn = (_userOpHash: string) => Promise<string>;

export type PassportSession = {
  aaAddress: `0x${string}`;
  eoaAddress: `0x${string}`;
};

type PassportSdkBundle = {
  // Loose-typed handles to keep this provider free of build-time
  // dependencies on `@gokite-network/auth` types — tests run without
  // the package and any signature drift between minor releases would
  // otherwise break the build.
  network: unknown;
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
    estimateUserOperation(
      _owner: string,
      _request: { targets: string[]; values?: bigint[]; callDatas: string[] },
    ): Promise<{
      sponsorshipAvailable: boolean;
      remainingSponsorships: number;
      paymasterAddress?: string;
      supportedTokens: Array<{ tokenAddress: string; tokenSymbol?: string; estimatedCost: string }>;
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
      chainName: "Kite",
    });
    const particleAuth = particle.auth;

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
    const aaSdk = new AaSdkCtor(
      "kite-testnet",
      env.rpcUrl,
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
    // GokiteNetwork.login() drives the Particle modal (passkey/email/social).
    await (bundle.network as { login: (_opts?: object) => Promise<unknown> }).login({});
    const aaAddress = (await bundle.smartAccount.getAddress()) as `0x${string}`;
    const eoaAddress = ((
      bundle.network as { user: { wallets?: Array<{ public_address: string }> } | null }
    ).user?.wallets?.[0]?.public_address ?? aaAddress) as `0x${string}`;
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
