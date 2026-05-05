/**
 * /allocators — public Allocator directory. DESIGN.md §9: serious
 * leaderboard. Sentinel and Helix pinned with the "Official Reference"
 * badge; third-party allocators trail by reputation.
 *
 * Reads live from Goldsky via `fetchAllocators`. Empty + error states
 * render in-grid so the page never spins forever.
 */

"use client";

import { useQuery } from "@tanstack/react-query";

import { AllocatorCard } from "@/components/allocators/AllocatorCard";
import { pinReferenceBrandsFirst } from "@/components/allocators/referenceBrands";
import { AppShell } from "@/components/chrome/AppShell";
import { PageHeader } from "@/components/chrome/PageHeader";
import { fetchAllocators } from "@/lib/goldsky";

const REFERENCE_SUPPORTED_CLASSES = ["Momentum", "Mean reversion", "Yield rotation"] as const;

export default function AllocatorsPage(): JSX.Element {
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["allocators"],
    queryFn: ({ signal }) => fetchAllocators(50, signal),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

  const rows = pinReferenceBrandsFirst(data ?? []);

  return (
    <AppShell>
      <PageHeader
        eyebrow="Public registry"
        title="Allocators"
        summary={
          <>
            Every registered allocator on Helios. Sentinel and Helix are the
            two reference brands operated by the Helios team; third-party
            allocators register on the same `AllocatorRegistry` and compete
            on the same reputation surface.
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

      {isLoading ? (
        <SkeletonGrid />
      ) : isError ? (
        <ErrorState message={(error as Error)?.message ?? "Subgraph unreachable."} />
      ) : rows.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {rows.map((row) => (
            <AllocatorCard
              key={row.id}
              row={row}
              // Phase-3 reference brands all support all three classes.
              // Third parties don't carry supported-class chips yet — the
              // schema lifts them out of `AllocatorRegistered` events but
              // not into the `Allocator` entity. Phase-5 follow-up.
              supportedClasses={
                row.isReferenceBrand || /helios (sentinel|helix)/i.test(row.name)
                  ? REFERENCE_SUPPORTED_CLASSES
                  : undefined
              }
            />
          ))}
        </div>
      )}
    </AppShell>
  );
}

function SkeletonGrid(): JSX.Element {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      {Array.from({ length: 2 }).map((_, i) => (
        <div
          key={i}
          className="h-44 animate-pulse rounded-md border border-surface-line bg-surface-elev/30"
        />
      ))}
    </div>
  );
}

function EmptyState(): JSX.Element {
  return (
    <div className="rounded-md border border-surface-line bg-surface-panel p-12 text-center text-sm text-fg-muted">
      No allocators registered yet. The first will appear here once
      `AllocatorRegistry.registerAllocator` lands on chain and the subgraph
      indexes it.
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
        deployed subgraph and reload.
      </p>
    </div>
  );
}
