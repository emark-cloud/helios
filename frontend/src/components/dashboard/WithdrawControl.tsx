/**
 * Withdraw control. DESIGN.md §9.3 — "always visible, never hidden
 * behind menus." Phase 1 wires the affordance and the explainer; the
 * actual `UserVault.withdraw` tx path is a Phase 2 follow-up
 * (matches the [PASSPORT-STUB] posture for the rest of the flow).
 */

"use client";

import { Numeric } from "@/components/atoms/Numeric";
import { formatUsd } from "@/lib/format";

export function WithdrawControl({ totalNavUsd }: { totalNavUsd: number }): JSX.Element {
  return (
    <div className="flex items-center justify-between gap-4 rounded-md border border-surface-line bg-surface-panel px-4 py-3">
      <div>
        <div className="text-[10px] uppercase tracking-[0.16em] text-fg-muted">Withdrawable</div>
        <div className="mt-1 text-base">
          <Numeric>{formatUsd(totalNavUsd, { cents: false })}</Numeric>
        </div>
      </div>
      <button
        type="button"
        // Phase 2 wires UserVault.withdraw via wagmi writeContract;
        // the affordance ships now so the dashboard surfaces the
        // custody guarantee from day one.
        disabled
        className="rounded-sm border border-fg-muted/40 px-3 py-2 font-mono text-xs uppercase tracking-[0.16em] text-fg-muted"
        title="Withdraw lands in Phase 2"
      >
        Withdraw
      </button>
    </div>
  );
}
