/**
 * /strategies — public Strategy Registry directory.
 * DESIGN.md §9.4: serious leaderboard. Sortable on every column,
 * filterable by class and chain.
 *
 * Reads live from Goldsky. Empty + error states render in-table so
 * the page never spins forever — the subgraph is the critical path
 * and we surface that explicitly.
 */

"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { AppShell } from "@/components/chrome/AppShell";
import { PageHeader } from "@/components/chrome/PageHeader";
import { StrategiesFilters } from "@/components/strategies/StrategiesFilters";
import { StrategiesTable } from "@/components/strategies/StrategiesTable";
import { fetchStrategies } from "@/lib/goldsky";

export default function StrategiesPage(): JSX.Element {
  const [classFilter, setClassFilter] = useState<string | null>(null);
  const [chainFilter, setChainFilter] = useState<number | null>(null);

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["strategies"],
    queryFn: ({ signal }) => fetchStrategies({ first: 100 }, signal),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

  const rows = data ?? [];

  return (
    <AppShell>
      <PageHeader
        eyebrow="Public registry"
        title="Strategies"
        summary={
          <>
            Every active strategy registered on Helios. Reputation, stake, and
            attested-trade counts read directly from the on-chain registries
            via the Helios subgraph.
          </>
        }
        actions={
          <button
            type="button"
            onClick={() => refetch()}
            className="rounded-sm border border-surface-line px-2 py-1 font-mono text-xs text-fg-secondary hover:border-amber/40 hover:text-fg-primary disabled:opacity-50"
            disabled={isFetching}
          >
            {isFetching ? "Refreshing…" : "Refresh"}
          </button>
        }
      />

      <div className="mb-4">
        <StrategiesFilters
          classFilter={classFilter}
          chainFilter={chainFilter}
          onClassFilter={setClassFilter}
          onChainFilter={setChainFilter}
        />
      </div>

      {isLoading ? (
        <SkeletonTable />
      ) : isError ? (
        <ErrorState message={(error as Error)?.message ?? "Subgraph unreachable."} />
      ) : (
        <StrategiesTable
          rows={rows}
          classFilter={classFilter}
          chainFilter={chainFilter}
        />
      )}
    </AppShell>
  );
}

function SkeletonTable(): JSX.Element {
  return (
    <div className="rounded-md border border-surface-line bg-surface-panel">
      <div className="h-8 border-b border-surface-line" />
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="h-10 animate-pulse border-b border-surface-line bg-surface-elev/30 last:border-b-0"
        />
      ))}
    </div>
  );
}

function ErrorState({ message }: { message: string }): JSX.Element {
  return (
    <div className="rounded-md border border-signal-negative-dim bg-surface-panel p-6 text-sm">
      <p className="text-fg-primary">Subgraph unreachable.</p>
      <p className="mt-1 font-mono text-xs text-fg-muted">{message}</p>
      <p className="mt-3 text-xs text-fg-secondary">
        Set <code className="font-mono text-fg-primary">NEXT_PUBLIC_GOLDSKY_ENDPOINT</code> to a
        deployed subgraph and reload. The Phase 1 endpoint is in <code>.env.example</code>.
      </p>
    </div>
  );
}
