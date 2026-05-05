/**
 * Allocator directory card. Bloomberg-density inside the card,
 * calm spacing around it. DESIGN.md §9: serious leaderboard.
 *
 * Always-visible:
 *   - Display name + reference-brand badge
 *   - Fee rate, supported-class chips, current users, total capital,
 *     reputation score, stake
 *   - Ranking-function one-sentence + "view code" link for
 *     reference brands; third parties show a short fallback line
 */

import Link from "next/link";
import type { Route } from "next";

import { Numeric } from "@/components/atoms/Numeric";
import { cn } from "@/lib/cn";
import { formatAddress, formatBpsAsPct, formatUsd } from "@/lib/format";
import type { AllocatorDirectoryRow } from "@/lib/goldsky";

import { referenceBrandFor } from "./referenceBrands";

const HELIX_FEE_BPS_THRESHOLD = 0; // visual only — never gates the row

export type AllocatorCardProps = {
  row: AllocatorDirectoryRow;
  /// Supported classes are not on the Allocator entity yet (the
  /// subgraph stores them per-event on AllocatorRegistration); the
  /// page passes them in as a static lookup until the schema lifts
  /// them into the entity. For Sentinel + Helix that's all three.
  supportedClasses?: ReadonlyArray<string>;
};

export function AllocatorCard({ row, supportedClasses }: AllocatorCardProps): JSX.Element {
  const brand = referenceBrandFor(row.name);
  const displayName = brand?.displayName ?? row.name;
  // Typed-routes (`experimental.typedRoutes`) needs a literal-prefix
  // `/allocators/` cast so the dynamic `[name]` segment satisfies
  // `RouteImpl`. `Route<>` from `next` is the official escape hatch.
  const detailHref = `/allocators/${encodeURIComponent(displayName)}` as Route;
  const reputation = readReputation(row.currentReputation);

  return (
    <Link
      href={detailHref}
      className={cn(
        "group block rounded-md border border-surface-line bg-surface-panel p-5",
        "hover:border-amber/40",
      )}
      aria-label={`Open ${displayName} detail`}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="font-display text-base font-semibold text-fg-primary group-hover:text-amber">
              {displayName}
            </h2>
            {row.isReferenceBrand || brand ? <ReferenceBadge /> : null}
            {!row.active ? (
              <span className="rounded-sm border border-signal-negative-dim px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.16em] text-signal-negative">
                Inactive
              </span>
            ) : null}
          </div>
          <p className="mt-2 text-sm text-fg-secondary">
            {brand?.rankingSummary ??
              "Third-party allocator. Ranking source not provided on chain."}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-fg-muted">
            Reputation
          </div>
          <Numeric tone={reputation > 50 ? "positive" : reputation > 0 ? "default" : "muted"}>
            {reputation.toFixed(1)}
          </Numeric>
        </div>
      </div>

      <dl className="mt-4 grid grid-cols-4 gap-x-4 gap-y-3 border-t border-surface-line pt-4">
        <Stat label="Fee" value={formatBpsAsPct(row.feeRateBps)} />
        <Stat label="Users" value={row.totalUsers.toString()} />
        <Stat
          label="Capital"
          value={formatUsd(usdcToUsd(row.totalCapitalManaged), { compact: true, cents: false })}
          hint="Cumulative event flow"
        />
        <Stat
          label="Stake"
          value={formatUsd(usdcToUsd(row.stakeAmount), { compact: true, cents: false })}
        />
      </dl>

      {supportedClasses && supportedClasses.length > 0 ? (
        <div className="mt-4 flex flex-wrap items-center gap-1.5 text-[11px]">
          {supportedClasses.map((cls) => (
            <span
              key={cls}
              className="rounded-sm border border-surface-line px-1.5 py-0.5 font-mono uppercase tracking-[0.12em] text-fg-secondary"
            >
              {cls}
            </span>
          ))}
        </div>
      ) : null}

      <div className="mt-4 flex items-center justify-between text-[11px] text-fg-muted">
        <span className="font-mono">Operator · {formatAddress(row.operator)}</span>
        {brand ? (
          <a
            href={brand.codeUrl}
            target="_blank"
            rel="noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="font-mono uppercase tracking-[0.12em] hover:text-amber"
          >
            View code →
          </a>
        ) : null}
        {/* Marker referenced by Playwright. Hidden from sighted users. */}
        <span className="sr-only" data-fee-bps={row.feeRateBps - HELIX_FEE_BPS_THRESHOLD} />
      </div>
    </Link>
  );
}

function ReferenceBadge(): JSX.Element {
  return (
    <span className="rounded-sm border border-amber/40 bg-amber/10 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.16em] text-amber">
      Official Reference
    </span>
  );
}

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}): JSX.Element {
  return (
    <div>
      <dt className="font-mono text-[10px] uppercase tracking-[0.16em] text-fg-muted">{label}</dt>
      <dd className="mt-1">
        <Numeric>{value}</Numeric>
        {hint ? <span className="ml-1 font-mono text-[10px] text-fg-muted">· {hint}</span> : null}
      </dd>
    </div>
  );
}

/// Subgraph capital amounts arrive as USDC integer strings (6
/// decimals). Display USD throughout: divide by 1e6.
function usdcToUsd(raw: string): number {
  const n = Number(raw);
  if (!Number.isFinite(n)) return 0;
  return n / 1e6;
}

function readReputation(raw: string): number {
  // Allocator reputation lands as a signed BigInt scaled 1e18.
  const n = Number(raw);
  if (!Number.isFinite(n)) return 0;
  // Heuristic: if it's already in the 0–100 bracket, leave it alone;
  // otherwise rescale.
  return Math.abs(n) > 1_000 ? n / 1e18 : n;
}
