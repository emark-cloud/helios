/**
 * Top strip — DESIGN.md §9.3. Four numerics: total NAV, today's P&L
 * (% + absolute), all-time P&L, fees-to-date. Tight rows inside, calm
 * spacing between the cards.
 *
 * "Today's P&L" isn't a Sentinel field today — we approximate it from
 * realized_pnl_usd as a placeholder. WS4 surfaces the slot; the
 * Sentinel-side daily breakdown is a Phase 2 follow-up.
 */

import { Numeric, toneFor } from "@/components/atoms/Numeric";
import { formatPct, formatUsd } from "@/lib/format";

export type DashboardTopStripProps = {
  totalNavUsd: number;
  totalCapitalUsd: number;
  realizedPnlUsd: number;
  feesPaidUsd: number;
};

export function DashboardTopStrip({
  totalNavUsd,
  totalCapitalUsd,
  realizedPnlUsd,
  feesPaidUsd,
}: DashboardTopStripProps): JSX.Element {
  const allTimePnl = totalNavUsd + realizedPnlUsd - totalCapitalUsd;
  const allTimePnlPct = totalCapitalUsd > 0 ? (allTimePnl / totalCapitalUsd) * 100 : 0;

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Stat label="Total NAV">
        <Numeric>{formatUsd(totalNavUsd, { cents: false })}</Numeric>
      </Stat>
      <Stat label="Capital deployed">
        <Numeric tone="muted">{formatUsd(totalCapitalUsd, { cents: false })}</Numeric>
      </Stat>
      <Stat label="All-time P&L">
        <div className="flex items-baseline gap-2">
          <Numeric tone={toneFor(allTimePnl)}>{formatUsd(allTimePnl, { cents: false })}</Numeric>
          <Numeric tone={toneFor(allTimePnl)} className="text-xs">
            ({formatPct(allTimePnlPct, { signed: true })})
          </Numeric>
        </div>
      </Stat>
      <Stat label="Fees paid">
        <Numeric tone="muted">{formatUsd(feesPaidUsd, { cents: false })}</Numeric>
      </Stat>
    </div>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }): JSX.Element {
  return (
    <div className="rounded-md border border-surface-line bg-surface-panel px-4 py-3">
      <div className="text-[10px] uppercase tracking-[0.16em] text-fg-muted">{label}</div>
      <div className="mt-1.5 text-lg">{children}</div>
    </div>
  );
}
