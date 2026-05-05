/**
 * /audit/[actor] — Reputation audit page (Phase 2 WS5).
 *
 * Surfaces every input the on-chain `componentsHash` commits to:
 *   - five §8.2 components (performance, risk, proof, stake, age)
 *   - per-window cohort stats (median, IQR) + raw vs normalized Sharpe
 *   - aggregate score (e4 → 0–100)
 *   - inputs (stake, attested trades, drawdown, proof rates)
 *
 * Read-only. Reads from the reputation engine HTTP API (not the subgraph)
 * because the engine recomputes from raw `Trade` events — keeping the
 * subgraph schema flat preserves the graph-cli 0.83.0 / graph-ts 0.31.0
 * pin (memory: Goldsky on Kite testnet rejects WASM 0xFC).
 */

"use client";

import { useQuery } from "@tanstack/react-query";

import { Numeric } from "@/components/atoms/Numeric";
import { ComponentBreakdown } from "@/components/audit/ComponentBreakdown";
import { CohortDistribution } from "@/components/audit/CohortDistribution";
import { AppShell } from "@/components/chrome/AppShell";
import { PageHeader } from "@/components/chrome/PageHeader";
import { formatAddress, formatStrategyClass } from "@/lib/format";
import {
  ReputationError,
  fetchAuditForActor,
  type AuditPayload,
  type ScoreComponents,
} from "@/lib/reputation";

export default function AuditPage({ params }: { params: { actor: string } }): JSX.Element {
  const actor = decodeURIComponent(params.actor);

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["audit", actor],
    queryFn: ({ signal }) => fetchAuditForActor(actor, signal),
    staleTime: 30_000,
    refetchInterval: 60_000,
    retry: (failureCount, err) => {
      if (err instanceof ReputationError && err.status === 404) return false;
      return failureCount < 2;
    },
  });

  return (
    <AppShell>
      <PageHeader
        eyebrow="Reputation audit · §8.2"
        title={data ? formatStrategyClass(data.declaredClass) : "Audit"}
        summary={
          <>
            Every input that produced this strategy&apos;s on-chain reputation score.
            The engine recomputes from raw <code className="font-mono text-fg-primary">Trade</code>{" "}
            events; the on-chain anchor stores the resulting score plus a{" "}
            <code className="font-mono text-fg-primary">componentsHash</code> that commits
            to the breakdown shown below.
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

      <div className="mb-6 flex flex-col gap-2 rounded-md border border-surface-line bg-surface-panel p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-[11px] uppercase tracking-[0.16em] text-fg-muted">Actor</p>
          <p className="mt-0.5 font-mono text-sm text-fg-primary" title={actor}>
            {formatAddress(actor)}
          </p>
        </div>
        {data ? (
          <div className="text-right">
            <p className="text-[11px] uppercase tracking-[0.16em] text-fg-muted">componentsHash</p>
            <p className="mt-0.5 break-all font-mono text-[11px] text-fg-secondary">
              {data.components_hash}
            </p>
          </div>
        ) : null}
      </div>

      {isLoading ? (
        <SkeletonAudit />
      ) : isError ? (
        <ErrorState
          status={error instanceof ReputationError ? error.status : null}
          message={(error as Error)?.message ?? "Reputation engine unreachable."}
          actor={actor}
        />
      ) : data ? (
        <AuditBody data={data} />
      ) : null}
    </AppShell>
  );
}

function AuditBody({ data }: { data: AuditPayload }): JSX.Element {
  const score100 = data.score_e4 / 100;
  const dominant = dominantComponent(data.components, data.weights);

  return (
    <div className="flex flex-col gap-6">
      {/* Aggregate score */}
      <section className="rounded-md border border-surface-line bg-surface-panel p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-[11px] uppercase tracking-[0.16em] text-fg-muted">Aggregate score</p>
            <div className="mt-1 flex items-baseline gap-2">
              <Numeric tone="amber" className="font-mono text-4xl">
                {score100.toFixed(2)}
              </Numeric>
              <span className="font-mono text-sm text-fg-muted">/ 100</span>
            </div>
          </div>
          <p className="max-w-md text-[11px] leading-snug text-fg-muted">
            Score = 0.40·perf + 0.25·risk + 0.15·proof + 0.10·stake + 0.10·age. Components
            below sum to this score; any change recomputes the{" "}
            <code className="font-mono text-fg-secondary">componentsHash</code> shown above.
          </p>
        </div>
      </section>

      {/* Five components */}
      <section>
        <h2 className="mb-3 text-[11px] uppercase tracking-[0.16em] text-fg-muted">
          Components
        </h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <ComponentBreakdown
            label="Performance"
            weight={data.weights.performance}
            value={data.components.performance}
            signed
            highlighted={dominant === "performance"}
            hint="Cohort-relative Sharpe, blended 7d/30d/90d"
          />
          <ComponentBreakdown
            label="Risk"
            weight={data.weights.risk}
            value={data.components.risk}
            highlighted={dominant === "risk"}
            hint="1 − clip(MaxDD90d / 5000bps)"
          />
          <ComponentBreakdown
            label="Proof"
            weight={data.weights.proof}
            value={data.components.proof}
            highlighted={dominant === "proof"}
            hint={
              data.proof_score_is_binary
                ? "ValidProofs / TotalAttempts (binary in v1 — only successful attestations are indexed, so 1.0 = no rejections seen, not 100% verified)"
                : "ValidProofs / TotalAttempts"
            }
          />
          <ComponentBreakdown
            label="Stake"
            weight={data.weights.stake}
            value={data.components.stake}
            highlighted={dominant === "stake"}
            hint="log-normalized vs class max stake"
          />
          <ComponentBreakdown
            label="Age"
            weight={data.weights.age}
            value={data.components.age}
            highlighted={dominant === "age"}
            hint="√(trades_attested / 1000)"
          />
        </div>
      </section>

      {/* Cohort distribution per window */}
      <section>
        <h2 className="mb-3 text-[11px] uppercase tracking-[0.16em] text-fg-muted">
          Cohort distribution
        </h2>
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
          <CohortDistribution
            windowLabel="7-day"
            rawSharpe={data.perf_breakdown.sharpe_7d}
            normalized={data.perf_breakdown.norm_7d}
            cohort={data.cohort.win_7d}
          />
          <CohortDistribution
            windowLabel="30-day"
            rawSharpe={data.perf_breakdown.sharpe_30d}
            normalized={data.perf_breakdown.norm_30d}
            cohort={data.cohort.win_30d}
          />
          <CohortDistribution
            windowLabel="90-day"
            rawSharpe={data.perf_breakdown.sharpe_90d}
            normalized={data.perf_breakdown.norm_90d}
            cohort={data.cohort.win_90d}
          />
        </div>
      </section>

      {/* Inputs */}
      <section>
        <h2 className="mb-3 text-[11px] uppercase tracking-[0.16em] text-fg-muted">
          Inputs
        </h2>
        <InputsTable data={data} />
      </section>
    </div>
  );
}

function InputsTable({ data }: { data: AuditPayload }): JSX.Element {
  const i = data.inputs;
  const stake = formatE18(i.stake_e18);
  const maxStake = formatE18(i.max_stake_in_class_e18);
  const proofRate =
    i.total_proof_attempts > 0
      ? `${i.valid_proofs} / ${i.total_proof_attempts}`
      : `${i.valid_proofs} / —`;

  const rows: Array<{ label: string; value: string; tone?: "default" | "muted" | "negative" }> = [
    { label: "Stake", value: `${stake}` },
    { label: "Max stake in class", value: maxStake, tone: "muted" },
    { label: "Trades attested", value: String(i.trades_attested) },
    {
      label: "Max drawdown (90d)",
      value: `${(i.max_drawdown_bps_90d / 100).toFixed(2)}%`,
      tone: i.max_drawdown_bps_90d > 0 ? "negative" : "muted",
    },
    { label: "Proofs (valid / attempts)", value: proofRate },
  ];

  return (
    <div className="overflow-hidden rounded-md border border-surface-line bg-surface-panel">
      <table className="w-full text-sm">
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.label}
              className="border-b border-surface-line last:border-b-0"
            >
              <td className="px-4 py-2.5 text-fg-secondary">{row.label}</td>
              <td className="px-4 py-2.5 text-right">
                <Numeric tone={row.tone ?? "default"} align="right" className="font-mono">
                  {row.value}
                </Numeric>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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

/** Format an e18 USDC-style integer string as a USD figure. Engine emits
 *  18-decimal scaled stake amounts to mirror the on-chain registry. */
function formatE18(raw: string): string {
  if (!raw || raw === "0") return "$0";
  // Engine emits big-int strings; for the sizes we expect (≤ ~1e9 USD),
  // a Number cast is safe (53-bit mantissa covers 10^15 cleanly).
  const n = Number(raw) / 1e18;
  if (!Number.isFinite(n)) return raw;
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(2)}k`;
  return `$${n.toFixed(2)}`;
}

function SkeletonAudit(): JSX.Element {
  return (
    <div className="flex flex-col gap-6">
      <div className="h-24 animate-pulse rounded-md border border-surface-line bg-surface-panel" />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={i}
            className="h-36 animate-pulse rounded-md border border-surface-line bg-surface-panel"
          />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className="h-40 animate-pulse rounded-md border border-surface-line bg-surface-panel"
          />
        ))}
      </div>
    </div>
  );
}

function ErrorState({
  status,
  message,
  actor,
}: {
  status: number | null;
  message: string;
  actor: string;
}): JSX.Element {
  if (status === 404) {
    return (
      <div className="rounded-md border border-surface-line bg-surface-panel p-6 text-sm">
        <p className="text-fg-primary">No reputation data for this actor.</p>
        <p className="mt-1 text-xs text-fg-muted">
          The engine has not yet computed a score for{" "}
          <code className="font-mono text-fg-secondary">{formatAddress(actor)}</code>. Strategies
          appear here once they accrue at least one attested trade.
        </p>
      </div>
    );
  }
  return (
    <div className="rounded-md border border-signal-negative-dim bg-surface-panel p-6 text-sm">
      <p className="text-fg-primary">Reputation engine unreachable.</p>
      <p className="mt-1 font-mono text-xs text-fg-muted">{message}</p>
      <p className="mt-3 text-xs text-fg-secondary">
        Set <code className="font-mono text-fg-primary">NEXT_PUBLIC_REPUTATION_URL</code> to a
        running reputation engine and reload. Default is{" "}
        <code className="font-mono">http://localhost:8002</code>.
      </p>
    </div>
  );
}
