/**
 * "Verify this proof yourself" modal — `DESIGN.md §12` celebrated tier.
 *
 * The command shape matches `scripts/verify-trade.js` exactly: positional
 * <tx-hash>, optional --rpc / --deployments overrides. Single dep
 * (`ethers@^6`); reads the on-chain TAV mapping to find the registered
 * class verifier and re-runs `verifyProof` against it.
 */

"use client";

import { useEffect, useRef, useState } from "react";

import { CloseIcon } from "@/components/icon";

export function VerifyYourselfModal({
  txHash,
  onClose,
}: {
  txHash: string | null;
  onClose: () => void;
}): JSX.Element | null {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!txHash) return;
    function onKey(e: KeyboardEvent): void {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    dialogRef.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [txHash, onClose]);

  if (!txHash) return null;

  const command = `node scripts/verify-trade.js ${txHash} --rpc $KITE_RPC_URL`;

  return (
    <div
      role="dialog"
      aria-modal
      aria-label="Verify this proof yourself"
      className="fixed inset-0 z-modal flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        tabIndex={-1}
        className="relative w-full max-w-xl rounded-md border border-amber/40 bg-surface-panel p-6 shadow-xl"
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="absolute right-3 top-3 text-fg-muted hover:text-fg-primary"
        >
          <CloseIcon className="h-4 w-4" />
        </button>

        <p className="text-[12px] uppercase tracking-[0.16em] text-amber">Verify yourself</p>
        <h2 className="mt-1 font-display text-xl text-fg-primary">
          Re-verify this Groth16 proof
        </h2>
        <p className="mt-2 text-sm text-fg-secondary">
          Run this off your own machine — the script reads the tx&apos;s public
          inputs, replays the proof against the on-chain verifier, and prints
          the verifier&apos;s exact return.
        </p>

        <CopyableCommand command={command} />

        <ul className="mt-4 space-y-1 text-xs text-fg-muted">
          <li>
            tx hash <code className="font-mono text-fg-secondary">{txHash}</code>
          </li>
          <li>
            verifier and class are read from the tx receipt; no manual
            args required
          </li>
          <li>
            single dependency: <code className="font-mono">ethers@^6</code>. Exit 0 on PASS, 1 on FAIL.
          </li>
        </ul>
      </div>
    </div>
  );
}

function CopyableCommand({ command }: { command: string }): JSX.Element {
  const [copied, setCopied] = useState(false);
  return (
    <div className="mt-4 flex items-center gap-2 rounded-sm border border-surface-line bg-surface-base p-3">
      <code className="flex-1 select-all font-mono text-xs text-fg-primary">{command}</code>
      <button
        type="button"
        onClick={() => {
          void navigator.clipboard.writeText(command);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}
        className="rounded-sm border border-amber/40 px-2 py-1 font-mono text-[12px] uppercase tracking-[0.12em] text-amber hover:border-amber/80"
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}
