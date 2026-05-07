/**
 * Active allocations table. DESIGN.md §9.3 — each row is one strategy
 * with name, chain, capital, NAV, P&L, drawdown, and last-rebalance
 * timestamp. Defunded rows get the red left-border per §10.2 (the
 * `data-defund-state="breaching"` selector lives in globals.css).
 */

"use client";

import { useRouter } from "next/navigation";
import type { Route } from "next";

import { ChainBadge } from "@/components/atoms/ChainBadge";
import { Numeric, toneFor } from "@/components/atoms/Numeric";
import { DigitTicker } from "@/components/motion/DigitTicker";
import {
  useSentinelStream,
  type DefundRowState,
} from "@/components/motion/SentinelStream";
import { useTableRowNav } from "@/hooks/useTableRowNav";
import { cn } from "@/lib/cn";
import {
  explorerAddressUrl,
  formatAddress,
  formatBpsAsPct,
  formatRelative,
  formatStrategyClass,
  formatUsd,
} from "@/lib/format";
import type { AllocationView } from "@/lib/sentinel";

/** Cap per-row stagger so the cascade lands in <1s even if the
 *  allocator deployed many strategies. Inside the cap, each row has
 *  its own 80ms delay (DESIGN §10.1). */
const MAX_CASCADE_DELAY_MS = 800;

export function AllocationsTable({ allocations }: { allocations: AllocationView[] }): JSX.Element {
  const { defundOf, repPulseOf } = useSentinelStream();
  const router = useRouter();
  const { selectedIndex } = useTableRowNav({
    rowCount: allocations.length,
    onActivate: (i) => {
      const target = allocations[i];
      if (target) router.push(`/strategies/${target.strategy_id.toLowerCase()}` as Route);
    },
  });
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
        <thead className="border-b border-surface-line text-[12px] uppercase tracking-[0.16em] text-fg-muted">
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
          {allocations.map((a, i) => {
            const sid = a.strategy_id.toLowerCase();
            const liveDefund = defundOf.get(sid);
            const repPulse = repPulseOf.get(sid)?.firedAt;
            return (
              <Row
                key={a.strategy_id}
                alloc={a}
                index={i}
                liveDefund={liveDefund}
                repPulseKey={repPulse}
                selected={i === selectedIndex}
              />
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Row({
  alloc,
  index,
  liveDefund,
  repPulseKey,
  selected,
}: {
  alloc: AllocationView;
  index: number;
  liveDefund: DefundRowState | undefined;
  repPulseKey: number | undefined;
  selected: boolean;
}): JSX.Element {
  const pnl = alloc.current_nav_usd - alloc.high_water_mark_usd;
  const pnlPct = alloc.high_water_mark_usd > 0 ? (pnl / alloc.high_water_mark_usd) * 100 : 0;
  const explorer = explorerAddressUrl(alloc.chain_id, alloc.strategy_id);

  // Live event takes precedence over the static `defunded` flag so a
  // mid-flight cascade reads the chain-watcher state (triggered →
  // armed → finalizing) rather than the polled REST snapshot.
  const defundState: DefundRowState | undefined =
    liveDefund ?? (alloc.defunded ? "breaching" : undefined);

  // Once the chain confirms `STRATEGY_DEFUNDED` the capital column
  // ticks down to zero across DESIGN §10.2's 2-second window.
  const targetCapital =
    defundState === "finalizing" || defundState === "breaching"
      ? 0
      : alloc.capital_deployed_usd;

  // 80ms per-row stagger. DESIGN §10.1 — cascade.
  const cascadeDelayMs = Math.min(index * 80, MAX_CASCADE_DELAY_MS);

  return (
    <tr
      className={cn(
        "border-b border-surface-line last:border-b-0",
        selected && "bg-surface-elev",
      )}
      data-defund-state={defundState}
      data-strategy-id={alloc.strategy_id}
      data-row-selected={selected ? "true" : undefined}
      aria-selected={selected ? "true" : undefined}
      style={{
        animation: "helios-cascade-row-in 1ms linear forwards",
        animationDelay: `${cascadeDelayMs}ms`,
        opacity: 0,
      }}
    >
      <td className="px-3 py-2.5">
        <div className="text-fg-primary">{formatStrategyClass(alloc.declared_class)}</div>
        <div className="font-mono text-[12px] text-fg-muted">
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
        <ChainBadge
          chainId={alloc.chain_id}
          pulseKey={repPulseKey}
          inFlight={repPulseKey != null}
        />
      </td>
      <td className="px-3 py-2.5 text-right">
        <DigitTicker
          value={targetCapital}
          format={(n) => formatUsd(n, { cents: false })}
          align="right"
        />
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
