/**
 * ProofBadge — the "acknowledged" tier of ZK visibility from
 * DESIGN.md §12: a small shield mark against each trade.
 *
 *   green shield  = valid proof
 *   outline shield = pending
 *   red shield    = failed (rare)
 *
 * The audit + judge surfaces upgrade this to the celebrated tier
 * (Phase 2/4); here we just stamp the row.
 */

import { ShieldIcon } from "@/components/icon";
import { cn } from "@/lib/cn";

export type ProofState = "valid" | "pending" | "failed";

const TONE: Record<ProofState, string> = {
  valid: "text-signal-positive",
  pending: "text-fg-muted",
  failed: "text-signal-negative",
};

const LABEL: Record<ProofState, string> = {
  valid: "ZK-attested",
  pending: "Proof pending",
  failed: "Proof failed",
};

export function ProofBadge({
  state,
  className,
  showLabel = false,
}: {
  state: ProofState;
  className?: string;
  showLabel?: boolean;
}): JSX.Element {
  return (
    <span
      className={cn("inline-flex items-center gap-1.5 align-middle", TONE[state], className)}
      title={LABEL[state]}
      aria-label={LABEL[state]}
    >
      <ShieldIcon filled={state === "valid"} className="h-3.5 w-3.5" />
      {showLabel ? <span className="font-mono text-xs uppercase tracking-wider">{LABEL[state]}</span> : null}
    </span>
  );
}
