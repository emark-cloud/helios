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
  type Hex,
} from "viem";
import { useAccount, useSignMessage, useWaitForTransactionReceipt, useWriteContract } from "wagmi";

import { AllocatorPicker } from "@/components/onboard/AllocatorPicker";
import { CommitmentSummary } from "@/components/onboard/CommitmentSummary";
import { CustomizationPanel } from "@/components/onboard/CustomizationPanel";
import { TemplatePicker } from "@/components/onboard/TemplatePicker";
import { usePassport } from "@/components/passport/PassportProvider";
import { addressesForChainId } from "@/lib/addresses";
import { readAllocatorChoice, writeAllocatorChoice } from "@/lib/onboard-storage";
import { type AuthMode } from "@/lib/passport";
import { postMetaStrategyTo, type AllocatorChoice, type MetaStrategyPayload } from "@/lib/sentinel";
import {
  DEFUND_PRESETS,
  TEMPLATES,
  type DefundForm,
  type TemplateForm,
  type TemplateKey,
} from "@/lib/templates";
import { IUserVaultAbi } from "@helios/contracts-abi";

const VALID_FOR_DAYS = 90;
// Allocator session TTL passed to delegateToAllocator. Capped at 30
// days to match `UserVault.maxSessionTTL` — the on-chain ceiling is
// 30d (2_592_000 s), so a 90d session would revert with
// `SessionTTLTooLong()` and silently drop the whole onboarding userOp
// at the bundler. Meta-strategy validity stays at 90d; the user
// re-delegates if the session lapses before the meta expires.
const ALLOCATOR_SESSION_TTL_SEC = 30 * 86_400;
// The deployed `mUSDC` mock on Kite testnet uses **18 decimals** (the
// MockERC20 default), not 6. parseUnits("1000", 6) = 1e9 wei, which
// is dust at 18 decimals — every onboard userOp landed with effectively
// zero capital, so the allocator decision loop never had anything to
// deploy. Confirmed via `cast call usdc decimals()` against
// 0xe8cf8a5711... on chain. Hardcoded rather than read from chain
// because the userOp builder runs synchronously off the form value.
const USDC_DECIMALS = 18;

const KITE_CHAIN_ID = Number(process.env.NEXT_PUBLIC_KITE_CHAIN_ID ?? "2368");

export function OnboardClient(): JSX.Element {
  const router = useRouter();
  const passport = usePassport();
  const { address: wagmiAddress, isConnected: wagmiConnected } = useAccount();
  const { signMessageAsync, isPending: isSigning } = useSignMessage();

  const [templateKey, setTemplateKey] = useState<TemplateKey>("balanced");
  const [form, setForm] = useState<TemplateForm>(TEMPLATES.balanced.form);
  const [defundForm, setDefundForm] = useState<DefundForm>(DEFUND_PRESETS.balanced);
  const [allocatorChoice, setAllocatorChoiceState] = useState<AllocatorChoice>("sentinel");

  // Hydrate from localStorage after mount.
  useEffect(() => {
    setAllocatorChoiceState(readAllocatorChoice());
  }, []);

  function setAllocatorChoice(next: AllocatorChoice): void {
    setAllocatorChoiceState(next);
    writeAllocatorChoice(next);
  }

  // Two-phase error model so the user never loses a signed payload to
  // a flaky Sentinel. `signing-failed` is unrecoverable (the wallet
  // rejected or the userOp itself reverted). `allocator-unreachable`
  // keeps the signed payload around so retry skips re-signing.
  type Signed = { payload: MetaStrategyPayload; auth: AuthMode; txHash: string | null };
  const [submitState, setSubmitState] = useState<
    | { kind: "idle" }
    | { kind: "submitting"; stage: string }
    | { kind: "ok"; user: string; auth: AuthMode; txHash: string | null }
    | { kind: "signing-failed"; message: string; raw: string | null }
    | { kind: "allocator-unreachable"; message: string; raw: string | null; signed: Signed }
  >({ kind: "idle" });
  const [showRaw, setShowRaw] = useState(false);

  function pickTemplate(next: TemplateKey): void {
    setTemplateKey(next);
    setForm(TEMPLATES[next].form);
    setDefundForm(DEFUND_PRESETS[next]);
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
      setSubmitState({
        kind: "signing-failed",
        message: classifySigningError(err, true),
        raw: errorMessage(err),
      });
    }
  }

  async function onSign(): Promise<void> {
    if (!userAddress) return;
    setShowRaw(false);
    // Replay path: a previous attempt signed successfully but Sentinel
    // POST failed. Don't burn another passkey/personal_sign — replay
    // the cached signed payload.
    if (submitState.kind === "allocator-unreachable") {
      void retryPost(submitState.signed);
      return;
    }

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
    let signed: MetaStrategyPayload;
    let txHash: string | null = null;
    try {
      if (passport.enabled) {
        // Single-passkey batched userOp lands the deposit + the
        // setMetaStrategy + the allocator delegation atomically.
        txHash = await sendOnboardingUserOp(passport, basePayload, defundForm);
        signed = { ...basePayload, signature: "0x", auth: "passport" };
      } else {
        const digest = canonicalDigest(basePayload);
        const sig = await signMessageAsync({ message: digest });
        signed = { ...basePayload, signature: sig, auth: "eip191" };
      }
    } catch (err) {
      setSubmitState({
        kind: "signing-failed",
        message: classifySigningError(err, passport.enabled),
        raw: errorMessage(err),
      });
      return;
    }
    await retryPost({ payload: signed, auth: signed.auth ?? "eip191", txHash });
  }

  async function retryPost(signed: Signed): Promise<void> {
    setSubmitState({ kind: "submitting", stage: "Recording with allocator…" });
    try {
      await postMetaStrategyTo(allocatorChoice, signed.payload);
      setSubmitState({
        kind: "ok",
        user: signed.payload.user_address,
        auth: signed.auth,
        txHash: signed.txHash,
      });
      router.push("/dashboard");
    } catch (err) {
      // Signature is intact — surface a retryable state so the user
      // doesn't have to re-sign (which would burn another passkey
      // prompt and roll the nonce).
      setSubmitState({
        kind: "allocator-unreachable",
        message: "Signed, but the allocator service didn't acknowledge. Retry without re-signing.",
        raw: errorMessage(err),
        signed,
      });
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
        <CustomizationPanel
          value={form}
          onChange={setForm}
          defundValue={defundForm}
          onDefundChange={setDefundForm}
        />
      </Section>

      <Section step="3" title="Allocator">
        <AllocatorPicker value={allocatorChoice} onChange={setAllocatorChoice} />
      </Section>

      <Section step="4" title="Sign">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
          <CommitmentSummary form={form} />
          <div className="flex flex-col gap-3">
            {!passport.enabled ? <MintDemoUsdcButton /> : null}
            <SignPanel
            connected={connected}
            isSigning={isSigning || submitState.kind === "submitting"}
            stage={submitState.kind === "submitting" ? submitState.stage : null}
            errorKind={
              submitState.kind === "signing-failed"
                ? "signing"
                : submitState.kind === "allocator-unreachable"
                  ? "allocator"
                  : null
            }
            errorMessage={
              submitState.kind === "signing-failed" || submitState.kind === "allocator-unreachable"
                ? submitState.message
                : null
            }
            errorRaw={
              submitState.kind === "signing-failed" || submitState.kind === "allocator-unreachable"
                ? submitState.raw
                : null
            }
            showRaw={showRaw}
            onToggleRaw={() => setShowRaw((v) => !v)}
            ok={submitState.kind === "ok"}
            canSubmit={Boolean(canSubmit)}
            onSign={() => void onSign()}
            onConnect={() => void onConnect()}
            authMode={passport.enabled ? "passport" : "eip191"}
            txHash={submitState.kind === "ok" ? submitState.txHash : null}
            isRetry={submitState.kind === "allocator-unreachable"}
            aaAddress={passport.session?.aaAddress ?? null}
            eoaAddress={passport.session?.eoaAddress ?? null}
          />
          </div>
        </div>
      </Section>
    </div>
  );
}

/**
 * Self-mint demo mUSDC for the connected EOA (non-Passport flow).
 *
 * The deployed mUSDC on Kite testnet is the permissionless
 * `MockERC20` (`contracts/test/mocks/MockERC20.sol`) — `mint` has
 * no access control, so any user can self-fund. The Passport flow
 * folds this mint into its userOp batch (see
 * `executePassportUserOp`); the wagmi/MetaMask flow doesn't have
 * a batch, so we surface a button. Mints 100k * 1e6 = 1e11 wei,
 * matching the frontend's `USDC_DECIMALS = 6` parsing convention
 * — enough headroom for the default 1k-USD form plus retries.
 */
function MintDemoUsdcButton(): JSX.Element | null {
  const { address, isConnected } = useAccount();
  const { writeContract, data: hash, error, isPending, reset } = useWriteContract();
  const { isLoading: isConfirming, isSuccess: isConfirmed } = useWaitForTransactionReceipt({
    hash,
  });
  const addrs = addressesForChainId(KITE_CHAIN_ID);
  if (!isConnected || !address || !addrs.usdc) return null;

  const usdc = addrs.usdc;
  const eoa = address;
  const onClick = (): void => {
    reset();
    writeContract({
      abi: [
        {
          type: "function",
          name: "mint",
          stateMutability: "nonpayable",
          inputs: [
            { name: "to", type: "address" },
            { name: "amount", type: "uint256" },
          ],
          outputs: [],
        },
      ] as const,
      address: usdc,
      functionName: "mint",
      args: [eoa, parseUnits("100000", USDC_DECIMALS)],
    });
  };

  const status = isPending
    ? "Confirm in your wallet…"
    : isConfirming
      ? "Mining…"
      : isConfirmed
        ? `Minted 100k mUSDC to ${eoa.slice(0, 6)}…${eoa.slice(-4)}`
        : error
          ? `Mint failed: ${error.message}`
          : null;

  return (
    <div className="rounded-md border border-surface-line bg-surface-panel p-4">
      <h3 className="text-[12px] uppercase tracking-[0.16em] text-fg-muted">Demo capital</h3>
      <p className="mt-2 text-xs text-fg-secondary">
        On Kite testnet mUSDC is a permissionless mock token — mint as much as you need to deposit.
      </p>
      <button
        type="button"
        onClick={onClick}
        disabled={isPending || isConfirming}
        className="mt-3 rounded-sm border border-surface-line bg-surface-elev px-3 py-2 font-mono text-xs uppercase tracking-[0.16em] text-fg-primary hover:border-amber hover:text-amber-bright disabled:cursor-not-allowed disabled:opacity-60"
      >
        Mint 100k demo mUSDC
      </button>
      {status ? (
        <p
          className={
            error
              ? "mt-2 font-mono text-[11px] text-signal-negative"
              : "mt-2 font-mono text-[11px] text-fg-secondary"
          }
        >
          {status}
        </p>
      ) : null}
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
  errorKind,
  errorMessage: errorMsg,
  errorRaw,
  showRaw,
  onToggleRaw,
  ok,
  canSubmit,
  onSign,
  onConnect,
  authMode,
  txHash,
  isRetry,
  aaAddress,
  eoaAddress,
}: {
  connected: boolean;
  isSigning: boolean;
  stage: string | null;
  errorKind: "signing" | "allocator" | null;
  errorMessage: string | null;
  errorRaw: string | null;
  showRaw: boolean;
  onToggleRaw: () => void;
  ok: boolean;
  canSubmit: boolean;
  onSign: () => void;
  onConnect: () => void;
  authMode: AuthMode;
  txHash: string | null;
  isRetry: boolean;
  aaAddress: string | null;
  eoaAddress: string | null;
}): JSX.Element {
  const passport = authMode === "passport";
  return (
    <div className="flex flex-col justify-between gap-3 rounded-md border border-surface-line bg-surface-panel p-6">
      <div>
        <h3 className="text-[12px] uppercase tracking-[0.16em] text-fg-muted">
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
      ) : passport && aaAddress ? (
        <div className="rounded-sm border border-surface-line bg-surface-elev px-3 py-2 text-[11px] text-fg-secondary">
          <div className="flex items-baseline justify-between gap-2">
            <span className="font-mono uppercase tracking-[0.16em] text-fg-muted">AA wallet</span>
            <span className="break-all font-mono text-fg-primary">{aaAddress}</span>
          </div>
          {eoaAddress && eoaAddress !== aaAddress ? (
            <div className="mt-1 flex items-baseline justify-between gap-2">
              <span className="font-mono uppercase tracking-[0.16em] text-fg-muted">Owner EOA</span>
              <span className="break-all font-mono text-fg-secondary">{eoaAddress}</span>
            </div>
          ) : null}
        </div>
      ) : null}

      {stage ? (
        <p className="rounded-sm border border-surface-line bg-surface-elev px-3 py-2 font-mono text-xs text-fg-secondary">
          {stage}
        </p>
      ) : null}

      {errorKind ? (
        <div
          role="alert"
          className={
            errorKind === "allocator"
              ? "rounded-sm border border-amber/40 bg-amber/10 px-3 py-2 text-xs text-amber-bright"
              : "rounded-sm border border-signal-negative-dim bg-surface-elev px-3 py-2 text-xs text-signal-negative"
          }
        >
          <p className="font-mono">
            {errorKind === "allocator" ? "Allocator unreachable" : "Signing failed"}
          </p>
          <p className="mt-1 text-fg-secondary">{errorMsg}</p>
          {errorRaw ? (
            <button
              type="button"
              onClick={onToggleRaw}
              className="mt-2 font-mono text-[12px] uppercase tracking-[0.16em] text-fg-muted hover:text-fg-primary"
            >
              {showRaw ? "Hide" : "Show"} technical detail
            </button>
          ) : null}
          {showRaw && errorRaw ? (
            <pre className="mt-2 overflow-x-auto rounded-sm border border-surface-line bg-surface-base px-2 py-1.5 font-mono text-[12px] text-fg-muted">
              {errorRaw}
            </pre>
          ) : null}
        </div>
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
        {isSigning
          ? "Working…"
          : isRetry
            ? "Retry — keep signature"
            : passport
              ? "Confirm with passkey"
              : "Sign meta-strategy"}
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
  defundForm: DefundForm,
): Promise<string> {
  if (!passport.enabled || passport.session === null) {
    throw new Error("Passport not signed in.");
  }
  const addrs = addressesForChainId(KITE_CHAIN_ID);
  if (!addrs.userVault || !addrs.usdc || !addrs.allocatorVault) {
    throw new Error(
      "kite-testnet deployment is missing userVault / usdc / allocatorVault — redeploy + regenerate addresses.",
    );
  }

  const aa = passport.session.aaAddress;
  // gokite-aa-sdk takes the **EOA** as the owner arg — it computes
  // the AA sender internally via getAccountAddress(owner, salt=2).
  // Passing `aa` here would treat our AA as the owner and deploy a
  // brand-new wallet at a different address whose `validateUserOp`
  // expects signatures from `aa`, not from the Particle EOA — the
  // userOp passes simulation but reverts during real execution.
  const eoa = passport.session.eoaAddress;
  const depositAmount = parseUnits(payload.max_capital_usd.toString(), USDC_DECIMALS);
  const metaStruct = formToContractStruct(payload, addrs.usdc, defundForm);

  // Read the AA's current `allocatorOf` so we can decide the batch
  // ordering. UserVault's HIGH-#5 tightening guard calls
  // `IAllocatorVaultForUser(allocator).userTotalDeployed(user)` from
  // setMetaStrategy if the user has metaSet=true and a non-zero
  // allocator. If the stored allocator is an EOA (no contract code)
  // the call reverts and every subsequent setMetaStrategy reverts.
  // For users in that bad state we MUST `delegateToAllocator(correct
  // contract)` before `setMetaStrategy` so the tightening check
  // resolves against a real contract. First-time users still need
  // setMetaStrategy first because delegateToAllocator requires
  // `metaSet=true`.
  let currentAllocator = "0x0000000000000000000000000000000000000000";
  const allocatorOfData = encodeFunctionData({
    abi: IUserVaultAbi,
    functionName: "allocatorOf",
    args: [aa],
  });
  try {
    const rpcUrl =
      process.env.NEXT_PUBLIC_KITE_RPC_URL ?? "https://rpc-testnet.gokite.ai";
    const resp = await fetch(rpcUrl, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        jsonrpc: "2.0",
        method: "eth_call",
        params: [{ to: addrs.userVault, data: allocatorOfData }, "latest"],
        id: 1,
      }),
    });
    const json = (await resp.json()) as { result?: string };
    if (json.result && json.result.length === 66) {
      currentAllocator = "0x" + json.result.slice(26);
    }
  } catch {
    /* fall through */
  }
  const hasExistingDelegation =
    currentAllocator.toLowerCase() !== "0x0000000000000000000000000000000000000000";
  console.info("[onboard] pre-batch state", { aa, currentAllocator, hasExistingDelegation });

  const setMetaCall = encodeFunctionData({
    abi: IUserVaultAbi,
    functionName: "setMetaStrategy",
    // The userOp is the user's authorization — the on-chain signature
    // arg becomes empty bytes. UserVault accepts 0x in Phase 1/2/3
    // (no on-chain verify); Phase 5 swaps for an EIP-1271 check
    // against the AA wallet.
    args: [metaStruct, "0x"],
  });
  const delegateCall = encodeFunctionData({
    abi: IUserVaultAbi,
    functionName: "delegateToAllocator",
    // Delegate to the AllocatorVault CONTRACT (not the operator
    // EOA). UserVault.setMetaStrategy's HIGH-#5 tightening guard
    // calls IAllocatorVaultForUser(allocator).userTotalDeployed —
    // an EOA address has no contract code, so the call reverts and
    // every subsequent setMetaStrategy reverts. The AllocatorVault
    // implements the view; the operator EOA stays the off-chain
    // signer that calls AllocatorVault.allocate.
    args: [addrs.allocatorVault, BigInt(ALLOCATOR_SESSION_TTL_SEC)],
  });
  // Returning user with an existing delegation: delegate FIRST so
  // the tightening guard in setMetaStrategy resolves against a real
  // contract. First-time user (no existing delegation): setMetaStrategy
  // FIRST because delegateToAllocator requires metaSet=true.
  const metaThenDelegate = !hasExistingDelegation;

  const callDatas: Hex[] = [
    // Mock-USDC self-mint. The deployed mUSDC on Kite testnet is the
    // permissionless `MockERC20` from `contracts/test/mocks/MockERC20.sol`
    // — `mint(address,uint256)` has no access control. Folding it into
    // the batch means a brand-new Passport AA wallet can self-fund the
    // exact amount it's about to deposit, with the Kite paymaster
    // sponsoring gas. No backend faucet, no operator key, no
    // pre-funding. v1 mUSDC is the demo capital float (Helios.md §6.1);
    // a mainnet stretch would replace this with a real-USDC funding
    // path (bridge / on-ramp).
    encodeFunctionData({
      abi: [
        {
          type: "function",
          name: "mint",
          stateMutability: "nonpayable",
          inputs: [
            { name: "to", type: "address" },
            { name: "amount", type: "uint256" },
          ],
          outputs: [],
        },
      ] as const,
      functionName: "mint",
      args: [aa, depositAmount],
    }),
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
    metaThenDelegate ? setMetaCall : delegateCall,
    metaThenDelegate ? delegateCall : setMetaCall,
  ];
  const targets: string[] = [
    addrs.usdc,
    addrs.usdc,
    addrs.userVault,
    addrs.userVault,
    addrs.userVault,
  ];

  // Bisect helper. URL `?probe=N` truncates the batch to the first N
  // calls — first userOp 1=mint, 2=mint+approve, 3=…+deposit,
  // 4=…+setMeta, 5=full (default). When the bundler silently drops
  // the op, walking probe up from 1 finds the reverting step.
  if (typeof window !== "undefined") {
    const probe = new URLSearchParams(window.location.search).get("probe");
    const n = probe ? Number(probe) : NaN;
    if (Number.isInteger(n) && n >= 1 && n < callDatas.length) {
      callDatas.length = n;
      targets.length = n;
      console.warn(`[onboard] PROBE MODE: truncated batch to first ${n} calls`);
    }
  }

  const bundle = passport.bundle;
  if (bundle === null) {
    throw new Error("Passport SDK did not initialise.");
  }

  const request = { targets, callDatas };

  // Canonical Kite AA-SDK flow (see
  // node_modules/gokite-aa-sdk/dist/example-token-paymaster.js):
  //
  //   const estimate = await sdk.estimateUserOperation(owner, request);
  //   const tokenAddress = estimate.sponsorshipAvailable
  //     ? ZERO_ADDRESS                       // free sponsorship branch
  //     : settlementToken;                   // billed-in-token branch
  //   const result = await sdk.sendUserOperationWithPayment(
  //     owner, request, estimate.userOp, tokenAddress, signFn);
  //
  // The high-level `sendUserOperationAndWait` doesn't expose the
  // fee-token arg and falls back to `supportedTokens[1]` (Test USD on
  // testnet) — the AA wallet never holds it and there's no
  // `approve(paymaster, …)` in our batch, so the bundler accepts
  // `eth_sendUserOperation`, returns a hash, and silently drops the
  // op. Bypassing through `sendUserOperationWithPayment` is what the
  // SDK's own example does, and it auto-prepends the paymaster
  // approve when the token branch is taken.
  const ZERO_ADDRESS = "0x0000000000000000000000000000000000000000" as const;

  // Paymaster preflight. The Kite testnet paymaster
  // (0x9Adcbf85...) caps free sponsorship at 5 userOps per AA.
  // After that it falls back to charging Test USD
  // (0x0fF53933...). The AA is unfunded by default, so the bundler
  // would just throw `AA33 reverted (InsufficientBalance)` from
  // estimateUserOperation with no actionable detail. Read the
  // paymaster + token state first and surface a precise message
  // before the SDK call.
  const PAYMASTER = "0x9Adcbf85D5c724611a490Ba9eDc4d38d6F39e92d" as const;
  const TEST_USD = "0x0fF5393387ad2f9f691FD6Fd28e07E3969e27e63" as const;
  try {
    const rpcUrl =
      process.env.NEXT_PUBLIC_KITE_RPC_URL ?? "https://rpc-testnet.gokite.ai";
    const ethCall = async (to: string, data: string): Promise<string | null> => {
      const r = await fetch(rpcUrl, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          jsonrpc: "2.0",
          method: "eth_call",
          params: [{ to, data }, "latest"],
          id: Math.floor(Math.random() * 1e9),
        }),
      });
      const j = (await r.json()) as { result?: string };
      return j.result ?? null;
    };
    // selectors (verified via `cast sig`):
    //   maxSponsoredTransactions() = 0x6bcce0ac
    //   userSponsorship(address)   = 0xf3ce37f6
    //   balanceOf(address) on TUSD = 0x70a08231
    const padAA = aa.toLowerCase().replace(/^0x/, "").padStart(64, "0");
    const [maxSponsored, userUsed, tusdBalance] = await Promise.all([
      ethCall(PAYMASTER, "0x6bcce0ac"),
      ethCall(PAYMASTER, "0xf3ce37f6" + padAA),
      ethCall(TEST_USD, "0x70a08231" + padAA),
    ]);
    const max = maxSponsored ? BigInt(maxSponsored) : 0n;
    const used = userUsed ? BigInt(userUsed) : 0n;
    const bal = tusdBalance ? BigInt(tusdBalance) : 0n;
    console.info("[onboard] paymaster preflight", {
      aa,
      maxSponsored: max.toString(),
      userSponsorshipUsed: used.toString(),
      remainingSponsorships: (max > used ? max - used : 0n).toString(),
      testUsdBalance: bal.toString(),
    });
    if (used >= max && bal === 0n) {
      throw new Error(
        `Paymaster sponsorship exhausted for this wallet (${used}/${max} free userOps used) and the AA holds no Test USD to pay for further userOps.\n\n`
          + `Fix one of these:\n`
          + `  • Sign in with a different passkey (incognito) — fresh AA, fresh 5 free userOps.\n`
          + `  • Send Test USD (${TEST_USD}) to ${aa} from the Kite faucet at https://faucet.gokite.ai.\n`
          + `  • Ask the Kite team to bump the sponsorship cap.`,
      );
    }
  } catch (preflightErr) {
    // Re-throw our own diagnostic; swallow RPC/network errors so a
    // flaky read doesn't block onboarding when the bundler would
    // actually accept the op.
    if (
      preflightErr instanceof Error
      && preflightErr.message.startsWith("Paymaster sponsorship exhausted")
    ) {
      throw preflightErr;
    }
    console.warn("[onboard] paymaster preflight read failed (non-fatal)", preflightErr);
  }

  // estimateUserOperation calls eth_estimateUserOperationGas on the
  // bundler, which runs full simulation including our batch. A revert
  // anywhere in the batch surfaces here as a generic "execution
  // reverted" with no per-call detail. Wrap so we log the request +
  // bundler response and per-call eth_call simulation against each
  // target, which lets us bisect which call is the culprit.
  let estimate: Awaited<ReturnType<typeof bundle.aaSdk.estimateUserOperation>>;
  try {
    estimate = await bundle.aaSdk.estimateUserOperation(eoa, request);
  } catch (err) {
    console.error("[onboard] estimateUserOperation reverted", {
      aa,
      eoa,
      request,
      error: err,
    });
    // Per-call bisection: simulate each (target, callData) standalone
    // from the AA address using eth_call. Standalone results don't
    // perfectly mirror the batched flow (state from prior calls
    // doesn't apply), but a revert that's INDEPENDENT of prior state
    // (e.g., paymaster precondition, token-not-deployed) will surface
    // here with the actual error data.
    const rpcUrl =
      process.env.NEXT_PUBLIC_KITE_RPC_URL ?? "https://rpc-testnet.gokite.ai";
    const probes: Array<{ idx: number; target: string; result: unknown }> = [];
    for (let i = 0; i < callDatas.length; i++) {
      try {
        const resp = await fetch(rpcUrl, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            jsonrpc: "2.0",
            method: "eth_call",
            params: [
              { from: aa, to: targets[i], data: callDatas[i] },
              "latest",
            ],
            id: i,
          }),
        });
        const json = (await resp.json()) as { result?: string; error?: unknown };
        probes.push({ idx: i, target: targets[i]!, result: json });
      } catch (probeErr) {
        probes.push({ idx: i, target: targets[i]!, result: probeErr });
      }
    }
    console.error("[onboard] per-call eth_call probes", probes);
    const detail =
      probes
        .filter((p) => {
          const r = p.result as { error?: unknown };
          return r?.error !== undefined;
        })
        .map((p) => {
          const r = p.result as { error?: { message?: string; data?: string } };
          return `call#${p.idx} → ${p.target}: ${r.error?.message ?? "?"} ${r.error?.data ?? ""}`;
        })
        .join("\n") || "no per-call reverts (batch-state-dependent failure)";
    // Per-call probes simulate each step in isolation, which gives
    // false positives for any call that depends on a prior step's
    // state change (e.g. deposit fails because the preceding approve
    // hasn't applied). Surface the *bundler* error too — that one runs
    // the full batch and is the authoritative revert reason. Chain the
    // probe summary as supplemental detail.
    const bundlerErr = err as {
      message?: string;
      shortMessage?: string;
      details?: string;
      cause?: { message?: string; data?: string };
      data?: string;
    };
    const bundlerSummary =
      bundlerErr.shortMessage
      ?? bundlerErr.message
      ?? bundlerErr.details
      ?? bundlerErr.cause?.message
      ?? "(no bundler message)";
    const bundlerData = bundlerErr.cause?.data ?? bundlerErr.data ?? "";
    throw new Error(
      `estimateUserOperation reverted.\nBundler: ${bundlerSummary}${bundlerData ? ` ${bundlerData}` : ""}\n\nPer-call probes (NOTE: each runs in isolation — a deposit failing here just means the prior approve hasn't applied; look at the bundler reason above first):\n${detail}`,
    );
  }
  // Diagnostic dump — when the bundler silently drops a userOp, the
  // SDK throws "UserOp polling timeout: 0x…" with no detail. Logging
  // the request + estimate to console gives us the userOp JSON, the
  // sponsorship status, the supportedTokens list, and the paymaster
  // address so a copy-paste from DevTools is enough to root-cause.
  // Costs nothing in the happy path; absent means we hit the throw
  // above (paymaster exhausted) or the SDK threw inside estimate.
  console.info(
    "[onboard] userOp estimate",
    JSON.stringify(
      {
        aa,
        eoa,
        targets,
        sponsorshipAvailable: estimate.sponsorshipAvailable,
        remainingSponsorships: estimate.remainingSponsorships,
        paymasterAddress: estimate.paymasterAddress,
        supportedTokens: estimate.supportedTokens,
        totalCostKITE: estimate.totalCostKITE,
        totalCostKITEFormatted: estimate.totalCostKITEFormatted,
        userOp: estimate.userOp,
      },
      // BigInt-safe replacer
      (_k, v: unknown) => (typeof v === "bigint" ? v.toString() : v),
      2,
    ),
  );

  let tokenAddress: string;
  if (estimate.sponsorshipAvailable) {
    tokenAddress = ZERO_ADDRESS;
  } else {
    const settlement = estimate.supportedTokens.find(
      (t) => t.tokenAddress.toLowerCase() !== ZERO_ADDRESS,
    );
    if (!settlement) {
      throw new Error(
        "Paymaster sponsorship exhausted and no fallback token configured. "
          + "Top up the AA wallet's settlement token or wait for sponsorship to refresh.",
      );
    }
    tokenAddress = settlement.tokenAddress;
  }

  let result: Awaited<ReturnType<typeof bundle.aaSdk.sendUserOperationWithPayment>>;
  try {
    result = await bundle.aaSdk.sendUserOperationWithPayment(
      eoa,
      request,
      estimate.userOp,
      tokenAddress,
      bundle.signFn,
    );
  } catch (err) {
    // The SDK throws "UserOp polling timeout: 0x<hash>" when
    // `eth_getUserOperationReceipt` keeps returning null. Pull the
    // hash out of the message and re-query the bundler ourselves —
    // if `eth_getUserOperationByHash` is also null the bundler
    // dropped the op (revert in actual execution). Surfaces the
    // hash + drop status into the rethrown error so the UI's
    // "technical detail" toggle exposes the diagnosis.
    const msg = err instanceof Error ? err.message : String(err);
    const hashMatch = msg.match(/0x[0-9a-fA-F]{64}/);
    if (hashMatch !== null) {
      const userOpHash = hashMatch[0];
      const bundlerUrl =
        process.env.NEXT_PUBLIC_AA_BUNDLER_URL
        ?? "https://bundler-service.staging.gokite.ai/rpc/";
      try {
        const [receipt, byHash] = await Promise.all([
          fetch(bundlerUrl, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
              jsonrpc: "2.0",
              method: "eth_getUserOperationReceipt",
              params: [userOpHash],
              id: 1,
            }),
          }).then((r) => r.json() as Promise<{ result: unknown }>),
          fetch(bundlerUrl, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
              jsonrpc: "2.0",
              method: "eth_getUserOperationByHash",
              params: [userOpHash],
              id: 2,
            }),
          }).then((r) => r.json() as Promise<{ result: unknown }>),
        ]);
        console.error("[onboard] bundler post-mortem", {
          userOpHash,
          receipt: receipt.result,
          byHash: byHash.result,
        });
        const dropped = receipt.result === null && byHash.result === null;
        const detail = dropped
          ? `Bundler dropped userOp ${userOpHash} (eth_getUserOperationByHash → null). Most likely cause: on-chain execution reverted post-simulation. Check console for the userOp JSON and try lowering max_capital_usd or removing one batch step.`
          : `userOp ${userOpHash} status: receipt=${JSON.stringify(receipt.result)}, byHash=${JSON.stringify(byHash.result)}`;
        throw new Error(`${msg}\n\n${detail}`);
      } catch (postMortemErr) {
        // Network failure querying bundler — re-throw original.
        if (postMortemErr instanceof Error && postMortemErr.message.includes(userOpHash)) {
          throw postMortemErr;
        }
        throw err;
      }
    }
    throw err;
  }
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
  defundForm: DefundForm,
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
    defundTwapBars: defundForm.defund_twap_bars,
    defundBondBps: defundForm.defund_bond_bps,
    defundConfirmBlocks: defundForm.defund_confirm_blocks,
  };
}

// Poseidon-derived class IDs, mirrored from `contracts/src/ClassIds.sol`
// and `packages/contracts-abi-py/src/helios_contracts_abi/class_ids.py`.
// keccak digests of the slugs overflow the BN254 scalar field and would
// trip snarkjs's `checkField` before any proof check ran, so we use
// Poseidon([int.from_bytes(slug, "big")]) instead. Drift between this
// table and `ClassIds.sol` is caught by the Foundry parity test
// (`test/ClassIds.t.sol`, re-derived via `vm.ffi`).
const CLASS_ID_BY_SLUG: Record<string, Hex> = {
  momentum_v1: "0x2a9aa442064b635baec37a7a259282faa5563a653a8325378d5676c6f04bc9dd",
  mean_reversion_v1: "0x18602f4f74172d545f5258541634e1a125c3a4e1227ee2a4cbee957d3490f1fb",
  yield_rotation_v1: "0x2e882135c6afc3bda02a9c8a7c6a351198d97599c804a2575a3d616073a87251",
};

function classSlugToBytes32(slug: string): Hex {
  const id = CLASS_ID_BY_SLUG[slug];
  if (id === undefined) {
    throw new Error(
      `unknown strategy class slug: ${slug} — extend CLASS_ID_BY_SLUG and ClassIds.sol`,
    );
  }
  return id;
}

function isPassportConfigComplete(): boolean {
  // The on-chain delegate target now reads from
  // `addressesForChainId(...).allocatorVault` (the deployed contract).
  // No env var to validate — onboarding is gated on the contract
  // being present in the deployments file, which the throw above
  // already enforces.
  return true;
}

function shorten(hash: string): string {
  if (hash.length < 12) return hash;
  return `${hash.slice(0, 6)}…${hash.slice(-4)}`;
}

function errorMessage(err: unknown): string {
  // Surface the stack trace alongside the message so the
  // "Show technical detail" toggle becomes a real diagnostic — the
  // SDKs throw bare strings like "Cannot read properties of undefined
  // (reading 'isTTY')" with no clue which chunk produced them. Also
  // emit to the console so the failure leaves a copyable trace in
  // DevTools regardless of UI state.
  if (typeof console !== "undefined") {
    console.error("[onboard] signing error", err);
  }
  if (err instanceof Error) {
    const head = err.message || err.name || "Error";
    return err.stack && err.stack !== head ? `${head}\n\n${err.stack}` : head;
  }
  if (typeof err === "string") return err;
  try {
    return JSON.stringify(err, null, 2);
  } catch {
    return "Onboarding failed.";
  }
}

/**
 * Map a thrown error from the signing path into a user-facing
 * message. The wallet/Passport SDKs throw a wide variety of strings;
 * we collapse them into "rejected" / "passkey failed" / "userOp
 * reverted" so the primary error line reads naturally and the raw
 * message stays available behind the technical-detail toggle.
 */
function classifySigningError(err: unknown, isPassport: boolean): string {
  const raw = errorMessage(err).toLowerCase();
  if (raw.includes("user reject") || raw.includes("user denied") || raw.includes("rejected")) {
    return isPassport
      ? "Passkey approval was cancelled. Try again to sign."
      : "Signature rejected in your wallet. Try again to sign.";
  }
  if (raw.includes("passkey") || raw.includes("webauthn")) {
    return "Passkey authentication failed. Try again, or check that the passkey for this site is still registered on your device.";
  }
  if (raw.includes("userop") || raw.includes("revert") || raw.includes("execution reverted")) {
    return "The on-chain userOp reverted. Your wallet was not charged; check the technical detail for the failure reason.";
  }
  return isPassport
    ? "Passkey signing did not complete."
    : "The wallet did not return a signature.";
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
