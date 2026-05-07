/**
 * /onboard — meta-strategy builder. Calm at the page level
 * (DESIGN.md §4.5 / §9.2). Three steps, top-down: pick a template,
 * adjust if you must, sign once.
 *
 * Phase 4 (WS-FE-1) ships two parallel paths:
 *
 *   - **Passport** (`NEXT_PUBLIC_USE_PASSPORT=1`): one passkey prompt
 *     covers a four-call batched userOp — `USDC.approve` →
 *     `UserVault.deposit` → `UserVault.setMetaStrategy` →
 *     `UserVault.delegateToAllocator`. The AA wallet IS the user, so
 *     the EIP-191 signature field becomes `0x` and the server
 *     records `auth: "passport"` instead.
 *   - **EIP-191** (default in dev / e2e): wagmi `personal_sign` over
 *     the canonical JSON digest, POSTed to Sentinel. No chain writes
 *     — `scripts/e2e-scenario.sh` deploys the user's deposit /
 *     setMetaStrategy / delegate path against anvil with deterministic
 *     test keys, so this surface only does the Sentinel handshake.
 *
 * Both paths POST the same `MetaStrategyPayload` shape to Sentinel
 * with the new `auth` enum so the dashboard / activity rail are
 * agnostic to which path produced the entry.
 */

"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  encodeFunctionData,
  erc20Abi,
  parseUnits,
  zeroAddress,
  type Hex,
} from "viem";
import { useAccount, useSignMessage } from "wagmi";

import { AllocatorPicker } from "@/components/onboard/AllocatorPicker";
import { CommitmentSummary } from "@/components/onboard/CommitmentSummary";
import { CustomizationPanel } from "@/components/onboard/CustomizationPanel";
import { TemplatePicker } from "@/components/onboard/TemplatePicker";
import { usePassport } from "@/components/passport/PassportProvider";
import { addressesForChainId } from "@/lib/addresses";
import { readAllocatorChoice, writeAllocatorChoice } from "@/lib/onboard-storage";
import { type AuthMode } from "@/lib/passport";
import { postMetaStrategyTo, type AllocatorChoice, type MetaStrategyPayload } from "@/lib/sentinel";
import { TEMPLATES, type TemplateForm, type TemplateKey } from "@/lib/templates";
import { IUserVaultAbi } from "@helios/contracts-abi";

const VALID_FOR_DAYS = 90;
// Allocator session TTL passed to delegateToAllocator. Matches the
// meta-strategy validity window above so the user revokes both
// surfaces in one motion if they let onboarding lapse.
const ALLOCATOR_SESSION_TTL_SEC = VALID_FOR_DAYS * 86_400;
// USDC has 6 decimals on every Helios chain (testnet test token,
// mainnet bridged USDC.e). Hardcoded rather than read from chain
// because the userOp builder runs synchronously off the form value.
const USDC_DECIMALS = 6;

const KITE_CHAIN_ID = Number(process.env.NEXT_PUBLIC_KITE_CHAIN_ID ?? "2368");
const SENTINEL_ALLOCATOR_ADDRESS = (process.env.NEXT_PUBLIC_SENTINEL_ALLOCATOR_ADDRESS
  ?? "") as `0x${string}`;

export function OnboardClient(): JSX.Element {
  const router = useRouter();
  const passport = usePassport();
  const { address: wagmiAddress, isConnected: wagmiConnected } = useAccount();
  const { signMessageAsync, isPending: isSigning } = useSignMessage();

  const [templateKey, setTemplateKey] = useState<TemplateKey>("balanced");
  const [form, setForm] = useState<TemplateForm>(TEMPLATES.balanced.form);
  const [allocatorChoice, setAllocatorChoiceState] = useState<AllocatorChoice>("sentinel");

  // Hydrate from localStorage after mount.
  useEffect(() => {
    setAllocatorChoiceState(readAllocatorChoice());
  }, []);

  function setAllocatorChoice(next: AllocatorChoice): void {
    setAllocatorChoiceState(next);
    writeAllocatorChoice(next);
  }

  const [submitState, setSubmitState] = useState<
    | { kind: "idle" }
    | { kind: "submitting"; stage: string }
    | { kind: "ok"; user: string; auth: AuthMode; txHash: string | null }
    | { kind: "error"; message: string }
  >({ kind: "idle" });

  function pickTemplate(next: TemplateKey): void {
    setTemplateKey(next);
    setForm(TEMPLATES[next].form);
  }

  // Effective wallet address: Passport AA when enabled + signed in,
  // else the wagmi-connected EOA (anvil/testnet operator path).
  const userAddress: `0x${string}` | undefined = passport.session?.aaAddress
    ?? (wagmiAddress as `0x${string}` | undefined);
  const connected = passport.enabled
    ? passport.session !== null
    : Boolean(wagmiConnected && wagmiAddress);

  async function onConnect(): Promise<void> {
    if (!passport.enabled) return; // EIP-191 path uses the existing WalletChip
    setSubmitState({ kind: "submitting", stage: "Awaiting passkey…" });
    try {
      await passport.login();
      setSubmitState({ kind: "idle" });
    } catch (err) {
      setSubmitState({ kind: "error", message: errorMessage(err) });
    }
  }

  async function onSign(): Promise<void> {
    if (!userAddress) return;
    const validUntil = Math.floor(Date.now() / 1000) + VALID_FOR_DAYS * 86_400;
    const nonce = mintNonce();

    const basePayload: MetaStrategyPayload = {
      ...form,
      user_address: userAddress,
      valid_until: validUntil,
      nonce,
      signature: "0x",
      auth: passport.enabled ? "passport" : "eip191",
    };

    setSubmitState({ kind: "submitting", stage: "Preparing meta-strategy…" });
    try {
      let signed: MetaStrategyPayload;
      let txHash: string | null = null;
      if (passport.enabled) {
        // Single-passkey batched userOp lands the deposit + the
        // setMetaStrategy + the allocator delegation atomically.
        // Sentinel still receives the off-chain payload so it can
        // mirror the meta-strategy without polling Goldsky.
        txHash = await sendOnboardingUserOp(passport, basePayload);
        signed = { ...basePayload, signature: "0x", auth: "passport" };
        setSubmitState({ kind: "submitting", stage: "Recording with allocator…" });
      } else {
        const digest = canonicalDigest(basePayload);
        const sig = await signMessageAsync({ message: digest });
        signed = { ...basePayload, signature: sig, auth: "eip191" };
      }
      await postMetaStrategyTo(allocatorChoice, signed);
      setSubmitState({ kind: "ok", user: userAddress, auth: signed.auth ?? "eip191", txHash });
      router.push("/dashboard");
    } catch (err) {
      setSubmitState({ kind: "error", message: errorMessage(err) });
    }
  }

  const canSubmit =
    connected
    && Boolean(userAddress)
    && form.allowed_assets.length > 0
    && form.allowed_strategy_classes.length > 0
    && (!passport.enabled || isPassportConfigComplete());

  return (
    <div className="flex flex-col gap-8">
      <Section step="1" title="Template">
        <TemplatePicker value={templateKey} onChange={pickTemplate} />
      </Section>

      <Section step="2" title="Constraints">
        <CustomizationPanel value={form} onChange={setForm} />
      </Section>

      <Section step="3" title="Allocator">
        <AllocatorPicker value={allocatorChoice} onChange={setAllocatorChoice} />
      </Section>

      <Section step="4" title="Sign">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
          <CommitmentSummary form={form} />
          <SignPanel
            connected={connected}
            isSigning={isSigning || submitState.kind === "submitting"}
            stage={submitState.kind === "submitting" ? submitState.stage : null}
            error={submitState.kind === "error" ? submitState.message : null}
            ok={submitState.kind === "ok"}
            canSubmit={Boolean(canSubmit)}
            onSign={() => void onSign()}
            onConnect={() => void onConnect()}
            authMode={passport.enabled ? "passport" : "eip191"}
            txHash={submitState.kind === "ok" ? submitState.txHash : null}
          />
        </div>
      </Section>
    </div>
  );
}

function Section({
  step,
  title,
  children,
}: {
  step: string;
  title: string;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <section>
      <div className="mb-3 flex items-baseline gap-3">
        <span className="font-mono text-xs text-fg-muted">{step}</span>
        <h2 className="font-display text-sm font-semibold uppercase tracking-[0.16em] text-fg-secondary">
          {title}
        </h2>
      </div>
      {children}
    </section>
  );
}

function SignPanel({
  connected,
  isSigning,
  stage,
  error,
  ok,
  canSubmit,
  onSign,
  onConnect,
  authMode,
  txHash,
}: {
  connected: boolean;
  isSigning: boolean;
  stage: string | null;
  error: string | null;
  ok: boolean;
  canSubmit: boolean;
  onSign: () => void;
  onConnect: () => void;
  authMode: AuthMode;
  txHash: string | null;
}): JSX.Element {
  const passport = authMode === "passport";
  return (
    <div className="flex flex-col justify-between gap-3 rounded-md border border-surface-line bg-surface-panel p-6">
      <div>
        <h3 className="text-[11px] uppercase tracking-[0.16em] text-fg-muted">
          {passport ? "One passkey prompt" : "Sign once"}
        </h3>
        <p className="mt-3 text-xs text-fg-secondary">
          {passport
            ? "Kite Passport will prompt your passkey once. The same signature lands the deposit, registers your meta-strategy, and delegates to the allocator."
            : "Your wallet will surface the meta-strategy as a personal_sign request. No on-chain transaction at this step."}
        </p>
      </div>

      {!connected ? (
        passport ? (
          <button
            type="button"
            onClick={onConnect}
            className="rounded-sm border border-amber bg-amber/10 px-3 py-2 font-mono text-xs uppercase tracking-[0.16em] text-amber-bright hover:bg-amber/20"
          >
            Sign in with Passport
          </button>
        ) : (
          <p className="rounded-sm border border-surface-line bg-surface-elev px-3 py-2 font-mono text-xs text-fg-secondary">
            Connect a wallet to sign.
          </p>
        )
      ) : null}

      {stage ? (
        <p className="rounded-sm border border-surface-line bg-surface-elev px-3 py-2 font-mono text-xs text-fg-secondary">
          {stage}
        </p>
      ) : null}

      {error ? (
        <p className="rounded-sm border border-signal-negative-dim bg-surface-elev px-3 py-2 font-mono text-xs text-signal-negative">
          {error}
        </p>
      ) : null}

      {ok ? (
        <p className="rounded-sm border border-signal-positive-dim bg-surface-elev px-3 py-2 font-mono text-xs text-signal-positive">
          {txHash
            ? `Signed (tx ${shorten(txHash)}). Routing to dashboard…`
            : "Signed. Routing to dashboard…"}
        </p>
      ) : null}

      <button
        type="button"
        onClick={onSign}
        disabled={!canSubmit || isSigning}
        className="rounded-md border border-amber bg-amber/10 px-4 py-2.5 font-mono text-sm uppercase tracking-[0.16em] text-amber-bright hover:bg-amber/20 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {isSigning ? "Working…" : passport ? "Confirm with passkey" : "Sign meta-strategy"}
      </button>
    </div>
  );
}

/**
 * Build + send the four-call onboarding userOp through Kite Passport.
 *
 * Returns the resulting tx hash for surfacing in the success panel.
 * Throws on any step failure — caller stamps the message into
 * `submitState.error`.
 */
async function sendOnboardingUserOp(
  passport: ReturnType<typeof usePassport>,
  payload: MetaStrategyPayload,
): Promise<string> {
  if (!passport.enabled || passport.session === null) {
    throw new Error("Passport not signed in.");
  }
  if (!SENTINEL_ALLOCATOR_ADDRESS) {
    throw new Error(
      "NEXT_PUBLIC_SENTINEL_ALLOCATOR_ADDRESS is unset — set the Sentinel EOA before onboarding.",
    );
  }
  const addrs = addressesForChainId(KITE_CHAIN_ID);
  if (!addrs.userVault || !addrs.usdc) {
    throw new Error(
      "kite-testnet deployment is missing userVault / usdc — redeploy + regenerate addresses.",
    );
  }

  const aa = passport.session.aaAddress;
  const depositAmount = parseUnits(payload.max_capital_usd.toString(), USDC_DECIMALS);
  const metaStruct = formToContractStruct(payload, addrs.usdc);

  const callDatas: Hex[] = [
    encodeFunctionData({
      abi: erc20Abi,
      functionName: "approve",
      args: [addrs.userVault, depositAmount],
    }),
    encodeFunctionData({
      abi: IUserVaultAbi,
      functionName: "deposit",
      args: [addrs.usdc, depositAmount],
    }),
    encodeFunctionData({
      abi: IUserVaultAbi,
      functionName: "setMetaStrategy",
      // The userOp is the user's authorization — the on-chain signature
      // arg becomes empty bytes. UserVault accepts 0x in Phase 1/2/3
      // (no on-chain verify); Phase 5 swaps for an EIP-1271 check
      // against the AA wallet.
      args: [metaStruct, "0x"],
    }),
    encodeFunctionData({
      abi: IUserVaultAbi,
      functionName: "delegateToAllocator",
      args: [SENTINEL_ALLOCATOR_ADDRESS, BigInt(ALLOCATOR_SESSION_TTL_SEC)],
    }),
  ];
  const targets: string[] = [addrs.usdc, addrs.userVault, addrs.userVault, addrs.userVault];

  const bundle = passport.bundle;
  if (bundle === null) {
    throw new Error("Passport SDK did not initialise.");
  }

  const request = { targets, callDatas };
  // Estimate first so the UI knows whether the paymaster sponsors gas;
  // even if we ignore the result here, the call surfaces a clear error
  // before we burn a passkey prompt on a doomed userOp.
  await bundle.aaSdk.estimateUserOperation(aa, request);

  const result = await bundle.aaSdk.sendUserOperationAndWait(
    aa,
    request,
    bundle.signFn,
  );
  if (result.status.status !== "success" && result.status.status !== "included") {
    throw new Error(
      result.status.reason
        ? `userOp failed: ${result.status.reason}`
        : `userOp failed: ${result.status.status}`,
    );
  }
  return result.status.transactionHash ?? result.userOpHash;
}

/**
 * Shape the Sentinel-flavoured form into the on-chain MetaStrategy
 * tuple. Mirrors `scripts/e2e_scenario.py:step_set_meta_strategy` —
 * zeros for the defund knobs let `MetaStrategyLib` substitute its
 * defaults on first write.
 */
function formToContractStruct(
  payload: MetaStrategyPayload,
  usdc: `0x${string}`,
): {
  metaStrategyHash: Hex;
  allowedStrategyClasses: Hex[];
  allowedAssets: `0x${string}`[];
  allowedChains: number[];
  maxCapital: bigint;
  maxPerStrategyBps: number;
  maxStrategiesCount: number;
  drawdownThresholdBps: number;
  maxFeeRateBps: number;
  rebalanceCadenceSec: bigint;
  validUntil: bigint;
  defundTwapBars: number;
  defundBondBps: number;
  defundConfirmBlocks: number;
} {
  return {
    // Forward-compatible placeholder — UserVault will recompute the
    // canonical hash from the struct once the Phase 5 EIP-1271 path
    // lands. Phase 4 chain code accepts an arbitrary hash here.
    metaStrategyHash: ("0x" + "00".repeat(32)) as Hex,
    allowedStrategyClasses: payload.allowed_strategy_classes.map((s) => classSlugToBytes32(s)),
    // Phase 1 templates store asset *symbols* not contract addresses
    // (templates predate the on-chain wiring). For the userOp we map
    // every entry to USDC — that mirrors the e2e harness's
    // single-asset universe and keeps the tuple legal. Phase 5 swaps
    // in a real symbol→address resolver.
    allowedAssets: payload.allowed_assets.map(() => usdc),
    allowedChains: payload.allowed_chains.map((c) => Number(c)),
    maxCapital: parseUnits(payload.max_capital_usd.toString(), USDC_DECIMALS),
    maxPerStrategyBps: payload.max_per_strategy_bps,
    maxStrategiesCount: payload.max_strategies_count,
    drawdownThresholdBps: payload.drawdown_threshold_bps,
    maxFeeRateBps: payload.max_fee_rate_bps,
    rebalanceCadenceSec: BigInt(payload.rebalance_cadence_sec),
    validUntil: BigInt(payload.valid_until),
    defundTwapBars: 0,
    defundBondBps: 0,
    defundConfirmBlocks: 0,
  };
}

function classSlugToBytes32(slug: string): Hex {
  // Match the keccak-derived byte32 IDs published by the contracts-abi
  // generator. Avoid importing `@helios/contracts-abi` SLUG_TO_BYTES32
  // on the JS side because the upstream Poseidon-derived ClassIds
  // (project_classids_poseidon memory) ship via the Python ABI module
  // only. The on-chain UserVault uses keccak256 in Phase 1 — see
  // scripts/e2e_scenario.py CLASS_*_BYTES32. Drop in once frontend
  // mirrors are in place; until then stub to zero so the userOp still
  // type-checks (the e2e harness exercises the real path).
  void slug;
  return ("0x" + "00".repeat(32)) as Hex;
}

function isPassportConfigComplete(): boolean {
  return Boolean(
    SENTINEL_ALLOCATOR_ADDRESS && SENTINEL_ALLOCATOR_ADDRESS !== zeroAddress,
  );
}

function shorten(hash: string): string {
  if (hash.length < 12) return hash;
  return `${hash.slice(0, 6)}…${hash.slice(-4)}`;
}

function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return "Onboarding failed.";
}

/**
 * Mint a fresh 53-bit replay-protection nonce. Bounded to
 * `Number.MAX_SAFE_INTEGER` so the value JSON-round-trips exactly
 * across the digest and the wire payload.
 */
function mintNonce(): number {
  const buf = new Uint32Array(2);
  crypto.getRandomValues(buf);
  const high = buf[0]! & 0x1f_ffff;
  const low = buf[1]!;
  return high * 0x1_0000_0000 + low;
}

/**
 * Canonical JSON digest of the payload (sans signature/auth).
 * Both fields vary by signing path and are not part of the hash.
 */
function canonicalDigest(payload: MetaStrategyPayload): string {
  const ordered: Record<string, unknown> = {};
  const keys = (Object.keys(payload) as Array<keyof MetaStrategyPayload>)
    .filter((k) => k !== "signature" && k !== "auth")
    .sort();
  for (const k of keys) {
    ordered[k] = payload[k];
  }
  return `Helios meta-strategy v1\n${JSON.stringify(ordered)}`;
}
