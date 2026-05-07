/**
 * Landing live-stats band — DESIGN.md §9.1.
 *
 * Four numbers in monospace, large. Refresh on a 30s cadence
 * (TanStack Query refetchInterval). On subgraph error the band
 * collapses to a quiet "—" placeholder; the page still renders.
 */

"use client";

import { useQuery } from "@tanstack/react-query";

import { Numeric } from "@/components/atoms/Numeric";
import { fetchLandingStats, type LandingStats } from "@/lib/goldsky";
import { formatUsd } from "@/lib/format";

export function LandingStatsBand(): JSX.Element {
  const query = useQuery<LandingStats, Error>({
    queryKey: ["landing-stats"],
    queryFn: ({ signal }) => fetchLandingStats(signal),
    refetchInterval: (q) => (q.state.error ? false : 30_000),
    staleTime: 15_000,
    retry: false,
  });

  const data = query.data;
  // Subgraph BigInt (capitalDeployed is e6 USDC). Convert to USD float
  // here so the formatter doesn't have to know.
  const totalUsd = data ? Number(BigInt(data.totalCapitalUsdE6)) / 1_000_000 : null;

  const cells: Array<{ label: string; value: string; help?: string }> = [
    {
      label: "Capital under attestation",
      value: totalUsd != null ? formatUsd(totalUsd, { compact: true, cents: false }) : "—",
      help: "Σ Allocation.capitalDeployed",
    },
    {
      label: "Active strategies",
      value: data ? data.activeStrategies.toString() : "—",
      help: "Strategy.active = true",
    },
    {
      label: "Attested trades",
      value: data ? data.attestedTrades.toString() : "—",
      help: "Σ Strategy.totalAttestedTrades",
    },
    {
      label: "Active allocators",
      value: data ? data.activeAllocators.toString() : "—",
      help: "Allocator.active = true",
    },
  ];

  return (
    <section
      aria-label="Live network statistics"
      className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-surface-line bg-surface-line sm:grid-cols-4"
    >
      {cells.map((cell) => (
        <div key={cell.label} className="flex flex-col gap-2 bg-surface-panel px-5 py-5">
          <span className="text-[10px] uppercase tracking-[0.18em] text-fg-muted">
            {cell.label}
          </span>
          <Numeric align="left" className="font-display text-3xl">
            {cell.value}
          </Numeric>
          {cell.help ? (
            <span className="font-mono text-[10px] text-fg-muted">{cell.help}</span>
          ) : null}
        </div>
      ))}
    </section>
  );
}
