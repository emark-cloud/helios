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
  // Kite testnet mUSDC is 18-decimal (Base/Arb mUSDC is 6-decimal but
  // the bulk of Phase-6 capital lives on Kite). Field name preserves the
  // legacy `_E6` suffix to avoid a subgraph schema bump.
  const totalUsd = data ? Number(BigInt(data.totalCapitalUsdE6) / 10n ** 12n) / 1_000_000 : null;

  const cells: Array<{ label: string; value: string }> = [
    {
      label: "Capital under attestation",
      value: totalUsd != null ? formatUsd(totalUsd, { compact: true, cents: false }) : "—",
    },
    {
      label: "Active strategies",
      value: data ? data.activeStrategies.toString() : "—",
    },
    {
      label: "Attested trades",
      value: data ? data.attestedTrades.toString() : "—",
    },
    {
      label: "Active allocators",
      value: data ? data.activeAllocators.toString() : "—",
    },
  ];

  return (
    <section
      aria-label="Live network statistics"
      className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-surface-line bg-surface-line sm:grid-cols-4"
    >
      {cells.map((cell) => (
        <div key={cell.label} className="flex flex-col gap-3 bg-surface-panel px-6 py-6">
          <span className="text-[12px] uppercase tracking-[0.18em] text-fg-muted">
            {cell.label}
          </span>
          <Numeric align="left" className="font-display text-3xl lg:text-4xl">
            {cell.value}
          </Numeric>
        </div>
      ))}
    </section>
  );
}
