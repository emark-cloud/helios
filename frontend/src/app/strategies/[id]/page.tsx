/**
 * /strategies/[id] — per-strategy detail surface (Phase 4 WS-FE-3).
 *
 * Self-contained data sheet per `DESIGN.md §9.5`. Pulls the manifest,
 * recent trades, current allocators, NAV history, and paramsHash
 * rotation timeline from the subgraph in a single GraphQL query
 * (`fetchStrategyDetail`), then renders sections in the canonical
 * top-down order: manifest → reputation → P&L → trades →
 * allocators → rotations → NAV.
 */

"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import type { Route } from "next";

import { Numeric } from "@/components/atoms/Numeric";
import { ComponentBreakdown } from "@/components/audit/ComponentBreakdown";
import { AppShell } from "@/components/chrome/AppShell";
import { PageHeader } from "@/components/chrome/PageHeader";
import { AllocatorsPanel } from "@/components/strategies/detail/AllocatorsPanel";
import { ManifestHeader } from "@/components/strategies/detail/ManifestHeader";
import { NavTimeline } from "@/components/strategies/detail/NavTimeline";
import { ParamsRotationTimeline } from "@/components/strategies/detail/ParamsRotationTimeline";
import { PnLCurve } from "@/components/strategies/detail/PnLCurve";
import { RecentTrades } from "@/components/strategies/detail/RecentTrades";
import { formatAddress, formatStrategyClass } from "@/lib/format";
import { fetchStrategyDetail } from "@/lib/goldsky";
import {
  ReputationError,
  fetchAuditForActor,
  type AuditPayload,
  type ScoreComponents,
} from "@/lib/reputation";

export default function StrategyDetailPage({
  params,
}: {
  params: { id: string };
}): JSX.Element {
  const id = decodeURIComponent(params.id);

  const detailQuery = useQuery({
    queryKey: ["strategy-detail", id],
    queryFn: ({ signal }) => fetchStrategyDetail(id, undefined, signal),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

  const auditQuery = useQuery({
    queryKey: ["strategy-audit", id],
    queryFn: ({ signal }) => fetchAuditForActor(id, signal),
    staleTime: 30_000,
    retry: (failureCount, err) =>
      err instanceof ReputationError && err.status === 404 ? false : failureCount < 2,
  });

  const strategy = detailQuery.data ?? null;
  const audit = auditQuery.data ?? null;

  return (
    <AppShell>
      <PageHeader
        eyebrow="Strategy detail"
        title={
          strategy
            ? `${formatStrategyClass(strategy.declaredClass)} · ${formatAddress(strategy.id)}`
            : "Strategy"
        }
        summary={
          <>
            Manifest, reputation breakdown, recent trades, current
            allocators, parameter changes, and the NAV timeline —
            every input the strategy makes available, in one read.
          </>
        }
        actions={
          strategy ? (
            <Link
              href={`/audit/strategy/${strategy.id.toLowerCase()}` as Route}
              className="rounded-sm border border-amber/40 px-2 py-1 font-mono text-xs text-amber hover:border-amber/80"
            >
              Full audit →
            </Link>
          ) : null
        }
      />

      {detailQuery.isLoading ? (
        <Skeleton />
      ) : detailQuery.isError ? (
        <ErrorState message={(detailQuery.error as Error)?.message ?? "Subgraph unreachable."} />
      ) : !strategy ? (
        <NotFound id={id} />
      ) : (
        <div className="flex flex-col gap-6">
          <ManifestHeader strategy={strategy} />

          <ReputationSection
            audit={audit}
            isLoading={auditQuery.isLoading}
            isError={auditQuery.isError}
            error={auditQuery.error as Error | undefined}
          />

          <PnLCurve snapshots={strategy.navSnapshots} />

          <RecentTrades
            strategyId={strategy.id}
            chainId={strategy.chainId}
            trades={strategy.trades}
          />

          <AllocatorsPanel strategy={strategy} />

          <ParamsRotationTimeline
            chainId={strategy.chainId}
            rotations={strategy.paramsRotations}
          />

          <NavTimeline snapshots={strategy.navSnapshots} />
        </div>
      )}
    </AppShell>
  );
}

function ReputationSection({
  audit,
  isLoading,
  isError,
  error,
}: {
  audit: AuditPayload | null;
  isLoading: boolean;
  isError: boolean;
  error: Error | undefined;
}): JSX.Element {
  if (isLoading) {
    return (
      <section>
        <h2 className="mb-2 text-[12px] uppercase tracking-[0.16em] text-fg-muted">
          Reputation breakdown
        </h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <div
              key={i}
              className="h-32 animate-pulse rounded-md border border-surface-line bg-surface-panel"
            />
          ))}
        </div>
      </section>
    );
  }
  if (isError || !audit) {
    const note =
      error instanceof ReputationError && error.status === 404
        ? "No reputation score yet — strategy needs at least one attested trade."
        : "Reputation engine unreachable. Showing on-chain data only.";
    return (
      <section>
        <h2 className="mb-2 text-[12px] uppercase tracking-[0.16em] text-fg-muted">
          Reputation breakdown
        </h2>
        <div className="rounded-md border border-surface-line bg-surface-panel p-4 text-xs text-fg-muted">
          {note}
        </div>
      </section>
    );
  }

  const dominant = dominantComponent(audit.components, audit.weights);

  return (
    <section>
      <header className="mb-2 flex items-baseline justify-between">
        <h2 className="text-[12px] uppercase tracking-[0.16em] text-fg-muted">
          Reputation breakdown
        </h2>
        <span className="font-mono text-[12px] uppercase tracking-[0.12em] text-fg-muted">
          aggregate{" "}
          <Numeric tone="amber" className="text-amber">
            {(audit.score_e4 / 100).toFixed(1)}
          </Numeric>{" "}
          / 100
        </span>
      </header>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <ComponentBreakdown
          label="Performance"
          weight={audit.weights.performance}
          value={audit.components.performance}
          signed
          highlighted={dominant === "performance"}
          hint="Cohort-relative Sharpe, blended 7d/30d/90d"
        />
        <ComponentBreakdown
          label="Risk"
          weight={audit.weights.risk}
          value={audit.components.risk}
          highlighted={dominant === "risk"}
          hint="1 − clip(MaxDD90d / 5000bps)"
        />
        <ComponentBreakdown
          label="Proof"
          weight={audit.weights.proof}
          value={audit.components.proof}
          highlighted={dominant === "proof"}
          hint="ValidProofs / TotalAttempts"
        />
        <ComponentBreakdown
          label="Stake"
          weight={audit.weights.stake}
          value={audit.components.stake}
          highlighted={dominant === "stake"}
          hint="log-normalized vs class max stake"
        />
        <ComponentBreakdown
          label="Age"
          weight={audit.weights.age}
          value={audit.components.age}
          highlighted={dominant === "age"}
          hint="√(trades_attested / 1000)"
        />
      </div>
    </section>
  );
}

function dominantComponent(
  components: ScoreComponents,
  weights: AuditPayload["weights"],
): keyof ScoreComponents {
  const contribs: Array<{ key: keyof ScoreComponents; value: number }> = [
    { key: "performance", value: weights.performance * components.performance },
    { key: "risk", value: weights.risk * components.risk },
    { key: "proof", value: weights.proof * components.proof },
    { key: "stake", value: weights.stake * components.stake },
    { key: "age", value: weights.age * components.age },
  ];
  return contribs.reduce((acc, c) => (Math.abs(c.value) > Math.abs(acc.value) ? c : acc)).key;
}

function Skeleton(): JSX.Element {
  return (
    <div className="flex flex-col gap-6">
      <div className="h-40 animate-pulse rounded-md border border-surface-line bg-surface-panel" />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={i}
            className="h-32 animate-pulse rounded-md border border-surface-line bg-surface-panel"
          />
        ))}
      </div>
      <div className="h-56 animate-pulse rounded-md border border-surface-line bg-surface-panel" />
      <div className="h-72 animate-pulse rounded-md border border-surface-line bg-surface-panel" />
    </div>
  );
}

function NotFound({ id }: { id: string }): JSX.Element {
  return (
    <div className="rounded-md border border-surface-line bg-surface-panel p-6 text-sm">
      <p className="text-fg-primary">Strategy not indexed.</p>
      <p className="mt-1 font-mono text-xs text-fg-muted">{id}</p>
      <p className="mt-3 text-xs text-fg-secondary">
        The Helios subgraph indexes strategies registered on{" "}
        <code className="font-mono text-fg-primary">StrategyRegistry</code>. If
        the address is correct, the strategy may not have completed registration
        yet.
      </p>
    </div>
  );
}

function ErrorState({ message }: { message: string }): JSX.Element {
  return (
    <div className="rounded-md border border-signal-negative-dim bg-surface-panel p-6 text-sm">
      <p className="text-fg-primary">Subgraph unreachable.</p>
      <p className="mt-1 font-mono text-xs text-fg-muted">{message}</p>
      <p className="mt-3 text-xs text-fg-secondary">
        Set <code className="font-mono text-fg-primary">NEXT_PUBLIC_GOLDSKY_ENDPOINT</code> and reload.
      </p>
    </div>
  );
}
