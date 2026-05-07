/**
 * /allocators/[name] — detail page for a single allocator. The route
 * param is the URL-decoded display name; the GraphQL filter resolves
 * either the production name ("Helios Sentinel") or the shadow form
 * ("Helios Sentinel-shadow") so the page works pre and post the
 * multi-sig brand flip.
 */

"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo } from "react";

import { AllocatorDecisionsTable } from "@/components/allocators/AllocatorDecisionsTable";
import { AllocatorReputationBreakdown } from "@/components/allocators/AllocatorReputationBreakdown";
import { referenceBrandFor } from "@/components/allocators/referenceBrands";
import { Numeric } from "@/components/atoms/Numeric";
import { AppShell } from "@/components/chrome/AppShell";
import { PageHeader } from "@/components/chrome/PageHeader";
import { fetchAllocatorByName } from "@/lib/goldsky";
import {
  explorerAddressUrl,
  formatAddress,
  formatBpsAsPct,
  formatTimestamp,
  formatUsd,
} from "@/lib/format";

export default function AllocatorDetailPage({
  params,
}: {
  params: { name: string };
}): JSX.Element {
  const decoded = decodeURIComponent(params.name);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["allocator", decoded],
    queryFn: ({ signal }) => fetchAllocatorByName(decoded, signal),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

  const brand = useMemo(() => referenceBrandFor(decoded), [decoded]);
  // Prefer the production display name from the brand registry so the
  // page header reads "Helios Helix" even when the on-chain name still
  // carries the "-shadow" suffix.
  const displayName = brand?.displayName ?? decoded;

  if (isLoading) {
    return (
      <AppShell>
        <PageHeader eyebrow="Allocator" title={displayName} summary="Loading…" />
        <div className="h-44 animate-pulse rounded-md border border-surface-line bg-surface-elev/30" />
      </AppShell>
    );
  }

  if (isError) {
    return (
      <AppShell>
        <PageHeader eyebrow="Allocator" title={displayName} />
        <ErrorState message={(error as Error)?.message ?? "Subgraph unreachable."} />
      </AppShell>
    );
  }

  if (!data) {
    return (
      <AppShell>
        <PageHeader eyebrow="Allocator" title={displayName} />
        <NotFound name={displayName} />
      </AppShell>
    );
  }

  const operatorChainId = inferChainId(data.decisions);
  const stake = usdcToUsd(data.stakeAmount);
  const capital = usdcToUsd(data.totalCapitalManaged);

  return (
    <AppShell>
      <PageHeader
        eyebrow={
          data.isReferenceBrand || brand ? "Allocator · Official Reference" : "Allocator"
        }
        title={displayName}
        summary={
          brand?.rankingSummary ??
          "Third-party allocator. Ranking source not provided on chain."
        }
        actions={
          brand ? (
            <a
              href={brand.codeUrl}
              target="_blank"
              rel="noreferrer"
              className="rounded-sm border border-surface-line px-2 py-1 font-mono text-xs uppercase tracking-[0.12em] text-fg-secondary hover:border-amber/40 hover:text-fg-primary"
            >
              View code →
            </a>
          ) : undefined
        }
      />

      {/* Header strip — operator, registered, fee, stake, users, capital. */}
      <dl className="mb-6 grid grid-cols-2 gap-4 rounded-md border border-surface-line bg-surface-panel p-5 md:grid-cols-6">
        <Stat
          label="Operator"
          value={
            <a
              href={
                operatorChainId !== null
                  ? explorerAddressUrl(operatorChainId, data.operator) ?? ""
                  : ""
              }
              target="_blank"
              rel="noreferrer"
              className="font-mono text-sm hover:text-amber"
            >
              {formatAddress(data.operator)}
            </a>
          }
        />
        <Stat label="Registered" value={formatTimestamp(Number(data.registeredAt))} />
        <Stat label="Fee" value={formatBpsAsPct(data.feeRateBps)} />
        <Stat
          label="Stake"
          value={formatUsd(stake, { compact: true, cents: false })}
        />
        <Stat label="Users" value={data.totalUsers.toString()} />
        <Stat
          label="Capital"
          value={formatUsd(capital, { compact: true, cents: false })}
        />
      </dl>

      {/* Reputation breakdown + delegated users, side by side on wide screens. */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <AllocatorReputationBreakdown currentReputation={data.currentReputation} />
        </div>
        <DelegatedUsers delegations={data.delegations} />
      </div>

      <section className="mt-6">
        <h2 className="mb-3 font-display text-sm font-semibold text-fg-primary">
          Recent decisions
        </h2>
        <AllocatorDecisionsTable decisions={data.decisions} chainId={operatorChainId ?? 2368} />
      </section>
    </AppShell>
  );
}

function DelegatedUsers({
  delegations,
}: {
  delegations: ReadonlyArray<{ id: string; capital: string; user: { id: string } }>;
}): JSX.Element {
  if (delegations.length === 0) {
    return (
      <aside className="rounded-md border border-surface-line bg-surface-panel p-5">
        <h2 className="font-display text-sm font-semibold text-fg-primary">
          Delegated users
        </h2>
        <p className="mt-2 text-xs text-fg-muted">
          No active delegations. Users that pick this allocator at /onboard
          will appear here.
        </p>
      </aside>
    );
  }
  return (
    <aside className="rounded-md border border-surface-line bg-surface-panel p-5">
      <h2 className="font-display text-sm font-semibold text-fg-primary">
        Delegated users · {delegations.length}
      </h2>
      <p className="mt-1 text-[12px] text-fg-muted">
        Capital shown is the most recent allocation event per user. P&L vs HWM
        will populate once `services/reputation` lifts components into the
        subgraph (Phase 5 follow-up).
      </p>
      <ul className="mt-3 divide-y divide-surface-line">
        {delegations.slice(0, 8).map((d) => (
          <li key={d.id} className="flex items-baseline justify-between py-2">
            <span className="font-mono text-xs text-fg-secondary">
              {formatAddress(d.user.id)}
            </span>
            <Numeric>{formatUsd(usdcToUsd(d.capital), { compact: true, cents: false })}</Numeric>
          </li>
        ))}
      </ul>
    </aside>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }): JSX.Element {
  return (
    <div>
      <dt className="font-mono text-[12px] uppercase tracking-[0.16em] text-fg-muted">{label}</dt>
      <dd className="mt-1 text-sm text-fg-primary">{value}</dd>
    </div>
  );
}

function NotFound({ name }: { name: string }): JSX.Element {
  return (
    <div className="rounded-md border border-surface-line bg-surface-panel p-8 text-center text-sm text-fg-muted">
      <p>
        No allocator named <span className="font-mono text-fg-primary">{name}</span> registered on
        chain. Check{" "}
        <Link href="/allocators" className="text-amber hover:underline">
          the directory
        </Link>{" "}
        for the canonical list.
      </p>
    </div>
  );
}

function ErrorState({ message }: { message: string }): JSX.Element {
  return (
    <div className="rounded-md border border-signal-negative-dim bg-surface-panel p-6 text-sm">
      <p className="text-fg-primary">Subgraph unreachable.</p>
      <p className="mt-1 font-mono text-xs text-fg-muted">{message}</p>
    </div>
  );
}

/// We don't carry the home chain on the Allocator entity; recent
/// decisions reference strategies which do. Use the most recent
/// decision's strategy.chainId; null when the allocator has no
/// decisions yet (the JSON falls back to Kite testnet).
function inferChainId(
  decisions: ReadonlyArray<{ strategy: { chainId: number } | null }>,
): number | null {
  for (const d of decisions) {
    if (d.strategy) return d.strategy.chainId;
  }
  return null;
}

function usdcToUsd(raw: string): number {
  const n = Number(raw);
  if (!Number.isFinite(n)) return 0;
  return n / 1e6;
}
