/**
 * Current-allocators panel — shows which allocators currently route
 * capital to this strategy, plus a mini-sunburst per allocator.
 *
 * Subgraph note: `Allocation.capitalDeployed` is per-event, not a
 * running total (memory: project_subgraph_bigint_limitation). We sum
 * across rows for the same `(allocator, strategy)` pair before
 * rendering the chart so the segment widths reflect aggregate capital.
 */

import Link from "next/link";
import type { Route } from "next";

import { MiniSunburst } from "@/components/sunburst";
import type { SunburstNode } from "@/components/sunburst";
import { Numeric } from "@/components/atoms/Numeric";
import {
  formatRelative,
  formatStrategyClass,
  formatUsd,
} from "@/lib/format";
import type { StrategyAllocationRow, StrategyDetail } from "@/lib/goldsky";

export function AllocatorsPanel({ strategy }: { strategy: StrategyDetail }): JSX.Element {
  const aggregated = aggregateByAllocator(strategy.allocations);

  return (
    <section data-testid="strategy-allocators">
      <h2 className="mb-2 text-[12px] uppercase tracking-[0.16em] text-fg-muted">
        Current allocators
      </h2>
      {aggregated.length === 0 ? (
        <div className="rounded-md border border-surface-line bg-surface-panel p-6 text-center text-sm text-fg-muted">
          No allocators are currently routing capital here.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {aggregated.map((entry) => (
            <AllocatorCard key={entry.allocatorId} entry={entry} strategy={strategy} />
          ))}
        </div>
      )}
    </section>
  );
}

type AggregatedEntry = {
  allocatorId: string;
  allocatorName: string;
  totalCapital: number;
  latestRebalanceTs: number;
  activeUsers: number;
  rows: StrategyAllocationRow[];
};

function aggregateByAllocator(rows: StrategyAllocationRow[]): AggregatedEntry[] {
  const byAlloc = new Map<string, AggregatedEntry>();
  for (const row of rows) {
    const id = row.allocator.id.toLowerCase();
    const usd = Number(row.capitalDeployed) / 1e6;
    const ts = Number(row.lastRebalanceAt);
    const isActive = row.defundedAt == null;

    const existing = byAlloc.get(id);
    if (existing) {
      existing.totalCapital += usd;
      existing.latestRebalanceTs = Math.max(existing.latestRebalanceTs, ts);
      if (isActive) existing.activeUsers += 1;
      existing.rows.push(row);
    } else {
      byAlloc.set(id, {
        allocatorId: id,
        allocatorName: row.allocator.name,
        totalCapital: usd,
        latestRebalanceTs: ts,
        activeUsers: isActive ? 1 : 0,
        rows: [row],
      });
    }
  }
  return [...byAlloc.values()].sort((a, b) => b.totalCapital - a.totalCapital);
}

function AllocatorCard({
  entry,
  strategy,
}: {
  entry: AggregatedEntry;
  strategy: StrategyDetail;
}): JSX.Element {
  const sunburstStrategies: SunburstNode[] = [
    {
      id: strategy.id,
      label: formatStrategyClass(strategy.declaredClass),
      weight: 1,
      chainId: strategy.chainId,
      declaredClass: strategy.declaredClass,
      capitalUsd: entry.totalCapital,
    },
  ];
  const sunburstAllocator: SunburstNode = {
    id: entry.allocatorId,
    label: entry.allocatorName,
    weight: 1,
    chainId: strategy.chainId,
  };
  const detailHref = `/allocators/${encodeURIComponent(entry.allocatorName)}` as Route;

  return (
    <div className="flex items-center gap-4 rounded-md border border-surface-line bg-surface-panel p-4">
      <MiniSunburst
        strategies={sunburstStrategies}
        allocator={sunburstAllocator}
        ariaLabel={`${entry.allocatorName} routes ${formatUsd(entry.totalCapital, { compact: true })} to this strategy`}
      />
      <div className="flex-1 min-w-0">
        <Link href={detailHref} className="text-sm text-fg-primary hover:text-amber">
          {entry.allocatorName}
        </Link>
        <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[12px]">
          <span className="text-fg-muted">Capital</span>
          <Numeric align="right">{formatUsd(entry.totalCapital, { compact: true, cents: false })}</Numeric>
          <span className="text-fg-muted">Users</span>
          <Numeric align="right">{entry.activeUsers}</Numeric>
          <span className="text-fg-muted">Last rebalance</span>
          <Numeric align="right" tone="muted">
            {entry.latestRebalanceTs > 0 ? formatRelative(entry.latestRebalanceTs) : "—"}
          </Numeric>
        </div>
      </div>
    </div>
  );
}
