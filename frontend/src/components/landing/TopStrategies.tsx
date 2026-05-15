/**
 * Landing — top strategies preview. DESIGN.md §8.1 ("foreground the
 * marketplace shape"): a tight 5-row table of the highest-reputation
 * strategies on the network. Click-through goes to /strategies/[id].
 *
 * Subgraph-driven, refreshed on the same 30s cadence as the stats band.
 * On error or empty: shows a quiet message; the page still renders.
 */

"use client";

import Link from "next/link";
import type { Route } from "next";
import { useQuery } from "@tanstack/react-query";

import { ChainBadge } from "@/components/atoms/ChainBadge";
import { Numeric } from "@/components/atoms/Numeric";
import { formatStrategyName } from "@/lib/addresses";
import {
  formatBpsAsPct,
  formatStrategyClass,
  formatUsd,
  mUsdcRawToUsd,
} from "@/lib/format";
import { fetchStrategies, type StrategyDirectoryRow } from "@/lib/goldsky";

export function TopStrategies(): JSX.Element {
  const query = useQuery<StrategyDirectoryRow[], Error>({
    queryKey: ["landing-top-strategies"],
    queryFn: ({ signal }) =>
      fetchStrategies(
        { first: 5, orderBy: "currentReputation", orderDir: "desc" },
        signal,
      ),
    refetchInterval: (q) => (q.state.error ? false : 30_000),
    staleTime: 15_000,
    retry: false,
  });

  const rows = query.data ?? [];

  return (
    <section className="flex flex-col gap-5">
      <div className="flex items-baseline justify-between border-b border-surface-line pb-2">
        <h2 className="font-mono text-[12px] uppercase tracking-[0.28em] text-fg-muted">
          Top strategies, by reputation
        </h2>
        <Link
          href="/strategies"
          className="font-mono text-[12px] uppercase tracking-[0.18em] text-fg-muted hover:text-fg-secondary"
        >
          See all →
        </Link>
      </div>
      <div className="overflow-x-auto rounded-md border border-surface-line bg-surface-panel">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-line text-[12px] uppercase tracking-[0.16em] text-fg-muted">
              <Th align="left">Strategy</Th>
              <Th align="left">Class</Th>
              <Th align="left">Chain</Th>
              <Th align="right">Fee</Th>
              <Th align="right">Stake</Th>
              <Th align="right">Reputation</Th>
            </tr>
          </thead>
          <tbody>
            {query.isLoading
              ? Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)
              : query.isError
                ? <MessageRow text="Subgraph unreachable. Stats below." />
                : rows.length === 0
                  ? <MessageRow text="No strategies registered yet." />
                  : rows.map((r) => <StrategyRow key={r.id} row={r} />)}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Th({
  children,
  align,
}: {
  children: React.ReactNode;
  align: "left" | "right";
}): JSX.Element {
  return (
    <th
      scope="col"
      className={`px-4 py-2.5 font-mono font-normal ${
        align === "right" ? "text-right" : "text-left"
      }`}
    >
      {children}
    </th>
  );
}

function StrategyRow({ row }: { row: StrategyDirectoryRow }): JSX.Element {
  const reputation = readReputation(row.currentReputation);
  const stake = mUsdcRawToUsd(row.stakeAmount, row.chainId);
  const href = `/strategies/${row.id.toLowerCase()}` as Route;

  return (
    <tr className="border-b border-surface-line last:border-b-0 transition-none hover:bg-surface-elev">
      <td className="px-4 py-3">
        <Link href={href} className="text-fg-primary hover:text-amber" title={row.id}>
          {formatStrategyName(row.id)}
        </Link>
      </td>
      <td className="px-4 py-3 text-fg-secondary">
        {formatStrategyClass(row.declaredClass)}
      </td>
      <td className="px-4 py-3">
        <ChainBadge chainId={row.chainId} />
      </td>
      <td className="px-4 py-3 text-right">
        <Numeric tone="muted" align="right">
          {formatBpsAsPct(row.feeRateBps)}
        </Numeric>
      </td>
      <td className="px-4 py-3 text-right">
        <Numeric tone="muted" align="right">
          {Number.isFinite(stake) && stake > 0
            ? formatUsd(stake, { compact: true })
            : "—"}
        </Numeric>
      </td>
      <td className="px-4 py-3 text-right">
        <Numeric
          tone={reputation > 50 ? "positive" : reputation > 0 ? "default" : "muted"}
          align="right"
        >
          {reputation.toFixed(1)}
        </Numeric>
      </td>
    </tr>
  );
}

function SkeletonRow(): JSX.Element {
  return (
    <tr className="border-b border-surface-line last:border-b-0">
      <td colSpan={6} className="px-4 py-3">
        <span className="block h-3 w-full animate-pulse rounded bg-surface-elev" />
      </td>
    </tr>
  );
}

function MessageRow({ text }: { text: string }): JSX.Element {
  return (
    <tr>
      <td colSpan={6} className="px-4 py-8 text-center text-sm text-fg-muted">
        {text}
      </td>
    </tr>
  );
}

function readReputation(raw: string): number {
  // Subgraph stores reputation as a fixed-point integer (BigInt string).
  // Phase 1 reputation is 0–100 — coerce both possible scales.
  const v = Number(raw) / 1e18;
  if (Number.isFinite(v) && v !== 0) return v;
  const direct = Number(raw);
  return Number.isFinite(direct) ? direct : 0;
}
