/**
 * Dashboard cascade — DESIGN.md §10.1.
 *
 * Mounts above the AllocationsTable. On first paint (or when the
 * allocator deploys a new round of capital), the sunburst grows from
 * the center via a single CSS scale keyframe, then the segments
 * settle. Per-row staggers happen inside `AllocationsTable`.
 *
 * The component is purely visual — all data comes in via props. It
 * decides the sunburst shape from the latest dashboard payload.
 */

"use client";

import { useMemo } from "react";

import { Sunburst } from "@/components/sunburst";
import type { SunburstNode } from "@/components/sunburst/useSunburstLayout";
import { formatStrategyClass, formatUsd } from "@/lib/format";
import type { AllocationView } from "@/lib/sentinel";

export type DashboardCascadeProps = {
  allocations: AllocationView[];
  allocatorName: string;
  allocatorId?: string;
  totalCapitalUsd: number;
};

export function DashboardCascade({
  allocations,
  allocatorName,
  allocatorId,
  totalCapitalUsd,
}: DashboardCascadeProps): JSX.Element {
  const { strategies, allocator } = useMemo(() => {
    const total = allocations.reduce((acc, a) => acc + a.capital_deployed_usd, 0);
    const sids: SunburstNode[] = allocations.map((a) => ({
      id: a.strategy_id,
      label: formatStrategyClass(a.declared_class),
      weight: total > 0 ? a.capital_deployed_usd / total : 1 / allocations.length,
      chainId: a.chain_id,
      declaredClass: a.declared_class,
      capitalUsd: a.capital_deployed_usd,
      navUsd: a.current_nav_usd,
    }));
    const a: SunburstNode = {
      id: allocatorId ?? "allocator",
      label: allocatorName,
      weight: 1,
      chainId: 2368,
      capitalUsd: total,
    };
    return { strategies: sids, allocator: a };
  }, [allocations, allocatorName, allocatorId]);

  return (
    <section
      aria-label="Capital cascade"
      className="rounded-md border border-surface-line bg-surface-panel p-5"
    >
      <div className="flex items-baseline justify-between">
        <h2 className="text-[12px] uppercase tracking-[0.16em] text-fg-muted">
          Cascade
        </h2>
        <span className="font-mono text-[12px] uppercase tracking-[0.16em] text-fg-muted">
          {strategies.length} strategies
        </span>
      </div>
      <div className="mt-4 flex flex-col items-center gap-4 lg:flex-row lg:items-start lg:gap-8">
        <div
          // helios-sunburst-grow keyframe lives in globals.css. The
          // motion budget tokens collapse to instant under
          // prefers-reduced-motion.
          style={{
            animation:
              "helios-sunburst-grow var(--tick-segment) cubic-bezier(0.2, 0, 0, 1) both",
            transformOrigin: "center",
          }}
          data-testid="dashboard-sunburst"
        >
          <Sunburst
            allocator={allocator}
            strategies={strategies}
            size={260}
            centerLabel={{
              primary: formatUsd(totalCapitalUsd, { compact: true, cents: false }),
              secondary: allocatorName,
            }}
            ariaLabel={`Cascade: ${allocatorName} routing ${formatUsd(
              totalCapitalUsd,
              { compact: true, cents: false },
            )} across ${strategies.length} strategies`}
          />
        </div>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 self-stretch text-xs lg:grid-cols-1 lg:self-center">
          <Stat label="Allocator" value={allocatorName} />
          <Stat label="Strategies" value={String(strategies.length)} />
          <Stat
            label="Capital deployed"
            value={formatUsd(totalCapitalUsd, { compact: true, cents: false })}
          />
        </dl>
      </div>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="text-fg-muted">{label}</dt>
      <dd className="font-mono text-fg-primary">{value}</dd>
    </div>
  );
}
