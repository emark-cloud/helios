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
import { useEffect, useMemo, useRef, useState } from "react";

import { AppShell } from "@/components/chrome/AppShell";
import { PageHeader } from "@/components/chrome/PageHeader";
import { StrategiesFilters } from "@/components/strategies/StrategiesFilters";
import { StrategiesTable } from "@/components/strategies/StrategiesTable";
import { useHotkeys } from "@/hooks/useHotkeys";
import { formatStrategyClass } from "@/lib/format";
import { fetchStrategies, type StrategyDirectoryRow } from "@/lib/goldsky";

export default function StrategiesPage(): JSX.Element {
  const [classFilter, setClassFilter] = useState<string | null>(null);
  const [chainFilter, setChainFilter] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const searchRef = useRef<HTMLInputElement | null>(null);

  useHotkeys([
    {
      combo: "/",
      handler: () => {
        searchRef.current?.focus();
        searchRef.current?.select();
      },
    },
    {
      combo: "escape",
      handler: () => {
        if (search) setSearch("");
        searchRef.current?.blur();
      },
      enabled: Boolean(search),
    },
  ]);

  // Auto-clear filters when leaving the page so a return visit isn't
  // pre-filtered by stale state (the filters don't persist via URL).
  useEffect(() => {
    return () => {
      setSearch("");
    };
  }, []);

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["strategies"],
    queryFn: ({ signal }) => fetchStrategies({ first: 100 }, signal),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

  const visibleRows = useMemo(() => filterBySearch(data ?? [], search), [data, search]);

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

      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <StrategiesFilters
          classFilter={classFilter}
          chainFilter={chainFilter}
          onClassFilter={setClassFilter}
          onChainFilter={setChainFilter}
        />
        <div className="flex items-center gap-2">
          <span className="text-[12px] uppercase tracking-[0.16em] text-fg-muted">
            Search
          </span>
          <input
            ref={searchRef}
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                e.preventDefault();
                if (search) {
                  setSearch("");
                }
                searchRef.current?.blur();
              }
            }}
            placeholder="Address / class"
            className="w-48 rounded-sm border border-surface-line bg-surface-panel px-2 py-1 font-mono text-[12px] text-fg-primary placeholder:text-fg-muted"
            aria-label="Search strategies"
          />
          <kbd className="rounded-sm border border-surface-line bg-surface-elev px-1.5 py-0.5 font-mono text-[12px] text-fg-muted">
            /
          </kbd>
        </div>
      </div>

      {isLoading ? (
        <SkeletonTable />
      ) : isError ? (
        <ErrorState message={(error as Error)?.message ?? "Subgraph unreachable."} />
      ) : (
        <StrategiesTable
          rows={visibleRows}
          classFilter={classFilter}
          chainFilter={chainFilter}
        />
      )}
    </AppShell>
  );
}

function filterBySearch(rows: StrategyDirectoryRow[], search: string): StrategyDirectoryRow[] {
  const q = search.trim().toLowerCase();
  if (!q) return rows;
  return rows.filter((r) => {
    if (r.id.toLowerCase().includes(q)) return true;
    if (formatStrategyClass(r.declaredClass).toLowerCase().includes(q)) return true;
    return false;
  });
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
