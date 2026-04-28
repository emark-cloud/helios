/**
 * Active allocations table. DESIGN.md §9.3 — each row is one strategy
 * with name, chain, capital, NAV, P&L, drawdown, and last-rebalance
 * timestamp. Defunded rows get the red left-border per §10.2 (the
 * `data-defund-state="breaching"` selector lives in globals.css).
 */

import { ChainBadge } from "@/components/atoms/ChainBadge";
import { Numeric, toneFor } from "@/components/atoms/Numeric";
import {
  explorerAddressUrl,
  formatAddress,
  formatBpsAsPct,
  formatRelative,
  formatStrategyClass,
  formatUsd,
} from "@/lib/format";
import type { AllocationView } from "@/lib/sentinel";

export function AllocationsTable({ allocations }: { allocations: AllocationView[] }): JSX.Element {
  if (allocations.length === 0) {
    // Reaching this branch means the user has a signed meta-strategy
    // (DashboardClient short-circuits the no-meta case to a 404 CTA);
    // the allocator just hasn't deployed capital yet.
    return (
      <div className="rounded-md border border-surface-line bg-surface-panel p-8 text-center text-sm text-fg-muted">
        Awaiting allocator decision. Sentinel ranks strategies on a 5-minute cadence and deploys capital when an eligible match is found.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-md border border-surface-line bg-surface-panel">
      <table className="w-full text-sm">
        <thead className="border-b border-surface-line text-[10px] uppercase tracking-[0.16em] text-fg-muted">
          <tr>
            <th className="px-3 py-2.5 text-left font-normal">Strategy</th>
            <th className="px-3 py-2.5 text-left font-normal">Chain</th>
            <th className="px-3 py-2.5 text-right font-normal">Capital</th>
            <th className="px-3 py-2.5 text-right font-normal">NAV</th>
            <th className="px-3 py-2.5 text-right font-normal">P&L %</th>
            <th className="px-3 py-2.5 text-right font-normal">Drawdown</th>
            <th className="px-3 py-2.5 text-right font-normal">Last rebalance</th>
          </tr>
        </thead>
        <tbody>
          {allocations.map((a) => (
            <Row key={a.strategy_id} alloc={a} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Row({ alloc }: { alloc: AllocationView }): JSX.Element {
  const pnl = alloc.current_nav_usd - alloc.high_water_mark_usd;
  const pnlPct = alloc.high_water_mark_usd > 0 ? (pnl / alloc.high_water_mark_usd) * 100 : 0;
  const explorer = explorerAddressUrl(alloc.chain_id, alloc.strategy_id);

  return (
    <tr
      className="border-b border-surface-line last:border-b-0"
      data-defund-state={alloc.defunded ? "breaching" : undefined}
    >
      <td className="px-3 py-2.5">
        <div className="text-fg-primary">{formatStrategyClass(alloc.declared_class)}</div>
        <div className="font-mono text-[11px] text-fg-muted">
          {explorer ? (
            <a href={explorer} target="_blank" rel="noreferrer" className="hover:text-amber">
              {formatAddress(alloc.strategy_id)}
            </a>
          ) : (
            formatAddress(alloc.strategy_id)
          )}
        </div>
      </td>
      <td className="px-3 py-2.5">
        <ChainBadge chainId={alloc.chain_id} />
      </td>
      <td className="px-3 py-2.5 text-right">
        <Numeric align="right">{formatUsd(alloc.capital_deployed_usd, { cents: false })}</Numeric>
      </td>
      <td className="px-3 py-2.5 text-right">
        <Numeric align="right">{formatUsd(alloc.current_nav_usd, { cents: false })}</Numeric>
      </td>
      <td className="px-3 py-2.5 text-right">
        <Numeric tone={toneFor(pnl)} align="right">
          {pnl >= 0 ? "+" : ""}
          {pnlPct.toFixed(2)}%
        </Numeric>
      </td>
      <td className="px-3 py-2.5 text-right">
        <Numeric tone={alloc.drawdown_bps > 0 ? "negative" : "muted"} align="right">
          {alloc.drawdown_bps > 0 ? `−${formatBpsAsPct(alloc.drawdown_bps)}` : "—"}
        </Numeric>
      </td>
      <td className="px-3 py-2.5 text-right">
        <Numeric tone="muted" align="right">
          {alloc.last_rebalance_ts ? formatRelative(alloc.last_rebalance_ts) : "—"}
        </Numeric>
      </td>
    </tr>
  );
}
