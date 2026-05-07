/**
 * Small clipboard-copy button. Reuse anywhere the UI displays a long
 * value the user might want to grab — addresses, hashes, endpoint URLs.
 */

"use client";

import { useState } from "react";

import { cn } from "@/lib/cn";

export type CopyButtonProps = {
  value: string;
  /** Accessible label. Defaults to "Copy to clipboard". */
  ariaLabel?: string;
  /** Override the visible "Copy" text (e.g. "Copy hash"). */
  label?: string;
  className?: string;
};

export function CopyButton({
  value,
  ariaLabel,
  label = "Copy",
  className,
}: CopyButtonProps): JSX.Element {
  const [copied, setCopied] = useState(false);

  async function copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard API gated by permissions / context — silently fail.
    }
  }

  return (
    <button
      type="button"
      onClick={copy}
      aria-label={ariaLabel ?? "Copy to clipboard"}
      className={cn(
        "shrink-0 rounded-sm border px-1.5 py-0.5 font-mono text-[12px] uppercase tracking-[0.18em] transition-none",
        copied
          ? "border-amber text-amber"
          : "border-surface-line text-fg-muted hover:border-fg-muted hover:text-fg-secondary",
        className,
      )}
    >
      {copied ? "Copied" : label}
    </button>
  );
}
