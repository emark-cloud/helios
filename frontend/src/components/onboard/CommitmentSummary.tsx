/**
 * Plainspoken summary above the sign button. DESIGN.md §6 voice — quiet
 * authority, no marketing copy. The user is about to sign a commitment;
 * the summary should make the meaningful constraints unmistakable.
 */

import { Numeric } from "@/components/atoms/Numeric";
import { formatBpsAsPct, formatStrategyClass } from "@/lib/format";
import type { TemplateForm } from "@/lib/templates";

export function CommitmentSummary({ form }: { form: TemplateForm }): JSX.Element {
  const classes = form.allowed_strategy_classes.map(formatStrategyClass).join(", ");
  const assets = form.allowed_assets.join(", ");
  const cadence = humanCadence(form.rebalance_cadence_sec);

  return (
    <div className="rounded-md border border-surface-line bg-surface-panel p-6">
      <h3 className="text-[11px] uppercase tracking-[0.16em] text-fg-muted">You are signing</h3>
      <ul className="mt-3 flex flex-col gap-2 text-sm text-fg-secondary">
        <li>
          Allocator routes capital across {classes} strategies trading {assets}.
        </li>
        <li>
          No single strategy holds more than{" "}
          <Numeric>{formatBpsAsPct(form.max_per_strategy_bps)}</Numeric> of your capital.
        </li>
        <li>
          A strategy that breaches{" "}
          <Numeric tone="negative">−{formatBpsAsPct(form.drawdown_threshold_bps)}</Numeric>{" "}
          drawdown can be defunded by anyone — including you, including the chain itself.
        </li>
        <li>
          Strategies charging more than{" "}
          <Numeric>{formatBpsAsPct(form.max_fee_rate_bps)}</Numeric> in performance fees are
          excluded from your allocation.
        </li>
        <li>The allocator may rebalance as often as every {cadence}.</li>
        <li>You retain custody. Withdraw is one click on the dashboard, no permission needed.</li>
      </ul>
    </div>
  );
}

function humanCadence(seconds: number): string {
  if (seconds >= 3_600 && seconds % 3_600 === 0) {
    const h = seconds / 3_600;
    return h === 1 ? "1 hour" : `${h} hours`;
  }
  const m = Math.round(seconds / 60);
  return m === 1 ? "1 minute" : `${m} minutes`;
}
