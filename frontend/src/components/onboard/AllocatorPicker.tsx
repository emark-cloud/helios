/**
 * Allocator picker step. WS6.B: two cards, Sentinel (default) and
 * Helix. Each shows fee rate, ranking-function summary, current
 * reputation, and a link to the `/allocators/[name]` detail page.
 *
 * Live reputation reads from Goldsky alongside other allocator
 * fields. While the subgraph is loading the cards still render with
 * the static brand metadata so the picker is never blocked on
 * subgraph latency.
 */

"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import type { Route } from "next";

import {
  pinReferenceBrandsFirst,
  referenceBrandFor,
} from "@/components/allocators/referenceBrands";
import { Numeric } from "@/components/atoms/Numeric";
import { cn } from "@/lib/cn";
import { formatBpsAsPct } from "@/lib/format";
import { fetchAllocators, type AllocatorDirectoryRow } from "@/lib/goldsky";
import type { AllocatorChoice } from "@/lib/sentinel";

const CHOICE_BY_BRAND: Record<string, AllocatorChoice> = {
  "helios sentinel": "sentinel",
  "helios sentinel-shadow": "sentinel",
  "helios helix": "helix",
  "helios helix-shadow": "helix",
};

/// Static fallback rows so the picker renders even when the subgraph
/// is unreachable or hasn't yet indexed the allocators. Default fees
/// match the on-chain registrations: Sentinel 500 bps, Helix 600 bps.
const FALLBACK_ROWS: ReadonlyArray<Pick<
  AllocatorDirectoryRow,
  "id" | "name" | "feeRateBps" | "currentReputation" | "totalUsers" | "isReferenceBrand"
>> = [
  {
    id: "0xsentinel",
    name: "Helios Sentinel",
    feeRateBps: 500,
    currentReputation: "0",
    totalUsers: 0,
    isReferenceBrand: true,
  },
  {
    id: "0xhelix",
    name: "Helios Helix",
    feeRateBps: 600,
    currentReputation: "0",
    totalUsers: 0,
    isReferenceBrand: true,
  },
];

export type AllocatorPickerProps = {
  value: AllocatorChoice;
  onChange: (_choice: AllocatorChoice) => void;
};

export function AllocatorPicker({ value, onChange }: AllocatorPickerProps): JSX.Element {
  const { data } = useQuery({
    queryKey: ["allocators", "picker"],
    queryFn: ({ signal }) => fetchAllocators(20, signal),
    staleTime: 30_000,
  });

  const liveRows = pinReferenceBrandsFirst(data ?? []).filter(
    (r) => CHOICE_BY_BRAND[r.name.toLowerCase()] !== undefined,
  );
  const rows = liveRows.length === 2 ? liveRows : FALLBACK_ROWS;

  return (
    <div
      className="grid grid-cols-1 gap-4 md:grid-cols-2"
      role="radiogroup"
      aria-label="Allocator"
    >
      {rows.map((row) => {
        const choice = CHOICE_BY_BRAND[row.name.toLowerCase()] ?? "sentinel";
        const brand = referenceBrandFor(row.name);
        const displayName = brand?.displayName ?? row.name;
        const selected = choice === value;
        return (
          <div
            key={choice}
            className={cn(
              "rounded-md border bg-surface-panel transition-none",
              selected
                ? "border-amber/60 bg-amber/[0.04] ring-1 ring-amber/40"
                : "border-surface-line hover:border-amber/40",
            )}
          >
            {/* Radio target — the upper card body. The `Details` link
                lives outside the radio per WCAG (focusable descendants
                of `role="radio"` aren't reachable via radiogroup
                keyboard nav). */}
            <button
              type="button"
              role="radio"
              aria-checked={selected}
              data-allocator-choice={choice}
              onClick={() => onChange(choice)}
              className="block w-full p-5 text-left"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="font-display text-sm font-semibold text-fg-primary">
                      {displayName}
                    </h3>
                    <span className="rounded-sm border border-amber/40 bg-amber/10 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.16em] text-amber">
                      Official Reference
                    </span>
                  </div>
                  <p className="mt-2 text-xs text-fg-secondary">
                    {brand?.rankingSummary}
                  </p>
                </div>
                <SelectedDot selected={selected} />
              </div>

              <dl className="mt-4 grid grid-cols-3 gap-x-4 gap-y-2 border-t border-surface-line pt-3">
                <Stat label="Fee" value={formatBpsAsPct(row.feeRateBps)} />
                <Stat label="Users" value={row.totalUsers.toString()} />
                <Stat label="Reputation" value={readReputation(row.currentReputation).toFixed(1)} />
              </dl>
            </button>
            <div className="flex items-center justify-between border-t border-surface-line px-5 py-2 text-[11px] text-fg-muted">
              <span className="font-mono uppercase tracking-[0.12em]">
                {selected ? "Selected" : "Tap to select"}
              </span>
              <Link
                // Phase-3 review MEDIUM: was `as never`, which silently
                // bypassed Next's typedRoutes. Cast to `Route` so the
                // dynamic `[name]` slot is enforced at the type level.
                href={`/allocators/${encodeURIComponent(displayName)}` as Route}
                className="font-mono uppercase tracking-[0.12em] hover:text-amber"
              >
                Details →
              </Link>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function SelectedDot({ selected }: { selected: boolean }): JSX.Element {
  return (
    <span
      className={cn(
        "mt-1 h-3 w-3 shrink-0 rounded-full border",
        selected ? "border-amber bg-amber/80" : "border-surface-line",
      )}
      aria-hidden
    />
  );
}

function Stat({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div>
      <dt className="font-mono text-[10px] uppercase tracking-[0.16em] text-fg-muted">{label}</dt>
      <dd className="mt-0.5">
        <Numeric>{value}</Numeric>
      </dd>
    </div>
  );
}

function readReputation(raw: string): number {
  const n = Number(raw);
  if (!Number.isFinite(n)) return 0;
  return Math.abs(n) > 1_000 ? n / 1e18 : n;
}
