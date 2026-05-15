/**
 * Top-5 allocator leaderboard for `/dashboard`. Reads the allocator
 * directory + 24h reputation deltas from Goldsky; pins Sentinel and
 * Helix to the top so the reference brands remain anchor points
 * regardless of where they sit on the score curve.
 *
 * Phase-3 plan WS6.C: a small, dense panel under the activity rail.
 * No links into `/allocators/*` here — the directory page is the
 * surface for that drilldown. Names stay clickable on the directory.
 */

"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import type { Route } from "next";

import {
  pinReferenceBrandsFirst,
  referenceBrandFor,
} from "@/components/allocators/referenceBrands";
import { Numeric, toneFor } from "@/components/atoms/Numeric";
import { formatBpsAsPct, formatUsd, mUsdcRawToUsd } from "@/lib/format";
import {
  fetchAllocatorLeaderboard,
  type AllocatorLeaderboardRow,
} from "@/lib/goldsky";

const TOP_N = 5;

export function AllocatorLeaderboard(): JSX.Element {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["allocator-leaderboard"],
    // Fetch a few extra rows so the pin step still has something to
    // promote when Sentinel/Helix sit just outside the natural top-5.
    queryFn: ({ signal }) => fetchAllocatorLeaderboard({ first: 25 }, signal),
    staleTime: 30_000,
  });

  return (
    <section data-testid="allocator-leaderboard">
      <header className="mb-2 flex items-baseline justify-between">
        <h2 className="text-[12px] uppercase tracking-[0.16em] text-fg-muted">
          Allocator leaderboard
        </h2>
        <Link
          href={"/allocators" as Route}
          className="font-mono text-[12px] uppercase tracking-[0.12em] text-fg-muted hover:text-amber"
        >
          View all →
        </Link>
      </header>

      {isError ? <ErrorState message={error.message} /> : null}
      {isLoading ? <LoadingState /> : null}
      {!isLoading && !isError ? (
        <Table rows={pickTopRows(data ?? [], TOP_N)} />
      ) : null}
    </section>
  );
}

/// Pin Sentinel + Helix to the top, then fill the remaining slots
/// with the highest-reputation rows that aren't already pinned.
export function pickTopRows(
  rows: AllocatorLeaderboardRow[],
  n: number,
): AllocatorLeaderboardRow[] {
  const ordered = pinReferenceBrandsFirst(rows);
  return ordered.slice(0, n);
}

function Table({ rows }: { rows: AllocatorLeaderboardRow[] }): JSX.Element {
  if (rows.length === 0) {
    return (
      <div className="rounded-md border border-surface-line bg-surface-panel p-6 text-center text-sm text-fg-muted">
        No allocators have indexed yet. Boot the subgraph and run the Phase 3 deploy.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-md border border-surface-line bg-surface-panel">
      <table className="w-full text-sm">
        <thead className="border-b border-surface-line text-[12px] uppercase tracking-[0.16em] text-fg-muted">
          <tr>
            <th className="px-3 py-2.5 text-left font-normal">#</th>
            <th className="px-3 py-2.5 text-left font-normal">Allocator</th>
            <th className="px-3 py-2.5 text-right font-normal">Reputation</th>
            <th className="px-3 py-2.5 text-right font-normal">24h Δ</th>
            <th className="px-3 py-2.5 text-right font-normal">Fee</th>
            <th className="px-3 py-2.5 text-right font-normal">Capital</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <Row key={row.id} row={row} rank={i + 1} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Row({
  row,
  rank,
}: {
  row: AllocatorLeaderboardRow;
  rank: number;
}): JSX.Element {
  const brand = referenceBrandFor(row.name);
  const displayName = brand?.displayName ?? row.name;
  const isReference = row.isReferenceBrand || Boolean(brand);
  const detailHref = `/allocators/${encodeURIComponent(displayName)}` as Route;

  const reputation = readReputation(row.currentReputation);
  const delta24h = sumDeltas(row.reputationUpdates);

  return (
    <tr
      className="border-b border-surface-line last:border-b-0"
      data-allocator-name={displayName}
    >
      <td className="px-3 py-2.5 font-mono text-[12px] text-fg-muted">{rank}</td>
      <td className="px-3 py-2.5">
        <div className="flex items-center gap-2">
          <Link
            href={detailHref}
            className="text-fg-primary hover:text-amber"
          >
            {displayName}
          </Link>
          {isReference ? (
            <span className="rounded-sm border border-amber/40 bg-amber/10 px-1.5 py-0.5 font-mono text-[12px] uppercase tracking-[0.16em] text-amber">
              Reference
            </span>
          ) : null}
        </div>
      </td>
      <td className="px-3 py-2.5 text-right">
        <Numeric
          align="right"
          tone={reputation > 50 ? "positive" : reputation > 0 ? "default" : "muted"}
        >
          {reputation.toFixed(1)}
        </Numeric>
      </td>
      <td className="px-3 py-2.5 text-right">
        <Numeric tone={toneFor(delta24h)} align="right">
          {delta24h === 0 ? "—" : `${delta24h >= 0 ? "+" : ""}${delta24h.toFixed(1)}`}
        </Numeric>
      </td>
      <td className="px-3 py-2.5 text-right">
        <Numeric align="right">{formatBpsAsPct(row.feeRateBps)}</Numeric>
      </td>
      <td className="px-3 py-2.5 text-right">
        <Numeric align="right">
          {formatUsd(usdcToUsd(row.totalCapitalManaged), { compact: true, cents: false })}
        </Numeric>
      </td>
    </tr>
  );
}

function LoadingState(): JSX.Element {
  return (
    <div className="space-y-1">
      {Array.from({ length: 3 }).map((_, i) => (
        <div
          key={i}
          className="h-9 animate-pulse rounded-sm border border-surface-line bg-surface-elev/30"
        />
      ))}
    </div>
  );
}

function ErrorState({ message }: { message: string }): JSX.Element {
  return (
    <div className="rounded-md border border-signal-negative-dim bg-surface-panel px-4 py-3 text-xs">
      <p className="text-fg-primary">
        Subgraph unreachable — <span className="font-mono text-fg-muted">{message}</span>
      </p>
    </div>
  );
}

function readReputation(raw: string): number {
  const n = Number(raw);
  if (!Number.isFinite(n)) return 0;
  return Math.abs(n) > 1_000 ? n / 1e18 : n;
}

function sumDeltas(updates: ReadonlyArray<{ delta: string }>): number {
  let acc = 0;
  for (const u of updates) {
    const n = Number(u.delta);
    if (!Number.isFinite(n)) continue;
    acc += Math.abs(n) > 1_000 ? n / 1e18 : n;
  }
  return acc;
}

// AllocatorRegistry is Kite-only — capital is Kite-mUSDC (18-dec).
function usdcToUsd(raw: string): number {
  return mUsdcRawToUsd(raw, 2368);
}
