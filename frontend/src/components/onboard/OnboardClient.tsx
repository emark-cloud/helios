/**
 * /onboard — meta-strategy builder. Calm at the page level
 * (DESIGN.md §4.5 / §9.2). Three steps, top-down: pick a template,
 * adjust if you must, sign once.
 *
 * Signing today is `[PASSPORT-STUB]`: an EOA EIP-191 signature over a
 * canonical JSON digest. The Sentinel records the signature for forward
 * compatibility with Kite Passport but does not verify it (see
 * services/sentinel/src/sentinel/schemas.py and
 * docs/kite-passport-notes.md).
 */

"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useAccount, useSignMessage } from "wagmi";

import { AllocatorPicker } from "@/components/onboard/AllocatorPicker";
import { CommitmentSummary } from "@/components/onboard/CommitmentSummary";
import { CustomizationPanel } from "@/components/onboard/CustomizationPanel";
import { TemplatePicker } from "@/components/onboard/TemplatePicker";
import { readAllocatorChoice, writeAllocatorChoice } from "@/lib/onboard-storage";
import { postMetaStrategyTo, type AllocatorChoice, type MetaStrategyPayload } from "@/lib/sentinel";
import { TEMPLATES, type TemplateForm, type TemplateKey } from "@/lib/templates";

const VALID_FOR_DAYS = 90;

export function OnboardClient(): JSX.Element {
  const router = useRouter();
  const { address, isConnected } = useAccount();
  const { signMessageAsync, isPending: isSigning } = useSignMessage();

  const [templateKey, setTemplateKey] = useState<TemplateKey>("balanced");
  const [form, setForm] = useState<TemplateForm>(TEMPLATES.balanced.form);
  const [allocatorChoice, setAllocatorChoiceState] = useState<AllocatorChoice>("sentinel");

  // Hydrate from localStorage after mount — `useState` initialiser
  // can't read `window` during SSR, and reading inside a `useEffect`
  // keeps server + initial-client markup identical (no hydration
  // mismatch).
  useEffect(() => {
    setAllocatorChoiceState(readAllocatorChoice());
  }, []);

  function setAllocatorChoice(next: AllocatorChoice): void {
    setAllocatorChoiceState(next);
    writeAllocatorChoice(next);
  }

  const [submitState, setSubmitState] = useState<
    | { kind: "idle" }
    | { kind: "submitting" }
    | { kind: "ok"; user: string }
    | { kind: "error"; message: string }
  >({ kind: "idle" });

  function pickTemplate(next: TemplateKey): void {
    setTemplateKey(next);
    setForm(TEMPLATES[next].form);
  }

  const validUntil = useMemo(
    () => Math.floor(Date.now() / 1000) + VALID_FOR_DAYS * 86_400,
    [],
  );

  async function onSign(): Promise<void> {
    if (!address) return;
    const payload: MetaStrategyPayload = {
      ...form,
      user_address: address,
      valid_until: validUntil,
      signature: "0x",
    };
    const digest = canonicalDigest(payload);

    setSubmitState({ kind: "submitting" });
    try {
      // [PASSPORT-STUB] EOA personal_sign over the canonical digest.
      // Swap to Passport `prepareSession` once the Kite Passport SDK
      // unblocks per docs/kite-passport-notes.md.
      const signature = await signMessageAsync({ message: digest });
      const signed = { ...payload, signature };
      // Route the POST to the chosen allocator's REST surface — Sentinel
      // (`:8001`) and Helix (`:8006`) expose the same shape but live
      // independently. WS6.B persists `allocatorChoice` in localStorage
      // so re-onboarding remembers.
      await postMetaStrategyTo(allocatorChoice, signed);
      setSubmitState({ kind: "ok", user: address });
      // DESIGN.md §10.1 — the cascade unfolds on the dashboard. Hand off.
      router.push("/dashboard");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Signing failed.";
      setSubmitState({ kind: "error", message });
    }
  }

  const canSubmit =
    isConnected && address && form.allowed_assets.length > 0 && form.allowed_strategy_classes.length > 0;

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
            connected={isConnected}
            isSigning={isSigning || submitState.kind === "submitting"}
            error={submitState.kind === "error" ? submitState.message : null}
            ok={submitState.kind === "ok"}
            canSubmit={Boolean(canSubmit)}
            onSign={() => void onSign()}
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
  error,
  ok,
  canSubmit,
  onSign,
}: {
  connected: boolean;
  isSigning: boolean;
  error: string | null;
  ok: boolean;
  canSubmit: boolean;
  onSign: () => void;
}): JSX.Element {
  return (
    <div className="flex flex-col justify-between gap-3 rounded-md border border-surface-line bg-surface-panel p-6">
      <div>
        <h3 className="text-[11px] uppercase tracking-[0.16em] text-fg-muted">Sign once</h3>
        <p className="mt-3 text-xs text-fg-secondary">
          Your wallet will surface the meta-strategy as a personal_sign request.{" "}
          <span className="font-mono text-fg-muted">[PASSPORT-STUB]</span> — Kite Passport
          replaces this once public access opens.
        </p>
      </div>

      {!connected ? (
        <p className="rounded-sm border border-surface-line bg-surface-elev px-3 py-2 font-mono text-xs text-fg-secondary">
          Connect a wallet to sign.
        </p>
      ) : null}

      {error ? (
        <p className="rounded-sm border border-signal-negative-dim bg-surface-elev px-3 py-2 font-mono text-xs text-signal-negative">
          {error}
        </p>
      ) : null}

      {ok ? (
        <p className="rounded-sm border border-signal-positive-dim bg-surface-elev px-3 py-2 font-mono text-xs text-signal-positive">
          Signed. Routing to dashboard…
        </p>
      ) : null}

      <button
        type="button"
        onClick={onSign}
        disabled={!canSubmit || isSigning}
        className="rounded-md border border-amber bg-amber/10 px-4 py-2.5 font-mono text-sm uppercase tracking-[0.16em] text-amber-bright hover:bg-amber/20 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {isSigning ? "Signing…" : "Sign meta-strategy"}
      </button>
    </div>
  );
}

/**
 * Canonical JSON digest of the payload (sans signature). Stable
 * key order matters because the allocator stores this digest as the
 * meta-strategy hash; both sides need to agree without any whitespace
 * or ordering ambiguity.
 */
function canonicalDigest(payload: MetaStrategyPayload): string {
  const ordered: Record<string, unknown> = {};
  const keys = (Object.keys(payload) as Array<keyof MetaStrategyPayload>)
    .filter((k) => k !== "signature")
    .sort();
  for (const k of keys) {
    ordered[k] = payload[k];
  }
  return `Helios meta-strategy v1\n${JSON.stringify(ordered)}`;
}
