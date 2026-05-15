/**
 * /audit/strategy/[id] — forensic per-strategy audit (Phase 4 WS-FE-4).
 *
 * Distinct from `/audit/[actor]` (the reputation-engine breakdown,
 * Phase 2). Surfaces every attested trade ever, paginated, with the ZK
 * proof treatment from `DESIGN.md §12`.
 *
 * The "verify yourself" CTA invokes `scripts/verify-trade.js` — single
 * file, single dep (`ethers@^6`), reads the on-chain TAV mapping and
 * re-runs `verifyProof` against the registered class verifier.
 */

"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import type { Route } from "next";
import { useState } from "react";

import { ChainBadge } from "@/components/atoms/ChainBadge";
import { CopyButton } from "@/components/atoms/CopyButton";
import { Numeric } from "@/components/atoms/Numeric";
import { ComponentBreakdown } from "@/components/audit/ComponentBreakdown";
import { AuditTradeRow } from "@/components/audit/strategy/AuditTradeRow";
import { VerifyYourselfModal } from "@/components/audit/strategy/VerifyYourselfModal";
import { AppShell } from "@/components/chrome/AppShell";
import { PageHeader } from "@/components/chrome/PageHeader";
import {
  explorerAddressUrl,
  formatAddress,
  formatStrategyClass,
  formatUsd,
  mUsdcRawToUsd,
} from "@/lib/format";
import { fetchStrategyAudit } from "@/lib/goldsky";
import {
  ReputationError,
  fetchAuditForActor,
  type AuditPayload,
  type ScoreComponents,
} from "@/lib/reputation";

const PAGE_SIZE = 50;

export default function StrategyAuditPage({
  params,
}: {
  params: { id: string };
}): JSX.Element {
  const id = decodeURIComponent(params.id);
  const [page, setPage] = useState(0);
  const [verifyTx, setVerifyTx] = useState<string | null>(null);

  const auditPageQuery = useQuery({
    queryKey: ["strategy-audit-page", id, page],
    queryFn: ({ signal }) =>
      fetchStrategyAudit(id, { first: PAGE_SIZE, skip: page * PAGE_SIZE }, signal),
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  });

  const reputationQuery = useQuery({
    queryKey: ["strategy-audit-reputation", id],
    queryFn: ({ signal }) => fetchAuditForActor(id, signal),
    staleTime: 30_000,
    retry: (failureCount, err) =>
      err instanceof ReputationError && err.status === 404 ? false : failureCount < 2,
  });

  const strategy = auditPageQuery.data ?? null;
  const reputation = reputationQuery.data ?? null;

  return (
    <AppShell>
      <PageHeader
        eyebrow="Trade audit"
        title={
          strategy
            ? `Audit · ${formatStrategyClass(strategy.declaredClass)}`
            : "Strategy audit"
        }
        summary={
          <>
            Every attested trade, paginated. Click a row to inspect the
            proof&apos;s public inputs and re-verify it locally. The reputation
            engine reads from this same stream.
          </>
        }
        actions={
          strategy ? (
            <div className="flex items-center gap-2">
              <Link
                href={`/strategies/${strategy.id.toLowerCase()}` as Route}
                className="rounded-sm border border-surface-line px-2 py-1 font-mono text-xs text-fg-secondary hover:border-amber/40 hover:text-fg-primary"
              >
                ← Strategy
              </Link>
              <a
                href={`/api/audit/strategy/${strategy.id.toLowerCase()}/dump`}
                target="_blank"
                rel="noreferrer"
                className="rounded-sm border border-surface-line px-2 py-1 font-mono text-xs text-fg-secondary hover:border-amber/40 hover:text-fg-primary"
              >
                Download JSON
              </a>
            </div>
          ) : null
        }
      />

      {auditPageQuery.isLoading && !strategy ? (
        <Skeleton />
      ) : auditPageQuery.isError ? (
        <ErrorState message={(auditPageQuery.error as Error)?.message ?? "Subgraph unreachable."} />
      ) : !strategy ? (
        <NotFound id={id} />
      ) : (
        <div className="flex flex-col gap-6">
          <HeaderCard strategy={strategy} />

          {reputation ? (
            <ReputationInputsPanel reputation={reputation} />
          ) : null}

          <TradesTable
            strategy={strategy}
            page={page}
            onPage={setPage}
            onVerify={setVerifyTx}
            isFetching={auditPageQuery.isFetching}
          />
        </div>
      )}

      <VerifyYourselfModal txHash={verifyTx} onClose={() => setVerifyTx(null)} />
    </AppShell>
  );
}

function HeaderCard({
  strategy,
}: {
  strategy: NonNullable<Awaited<ReturnType<typeof fetchStrategyAudit>>>;
}): JSX.Element {
  const explorer = explorerAddressUrl(strategy.chainId, strategy.id);
  const operatorExplorer = explorerAddressUrl(strategy.chainId, strategy.operator);
  const stake = mUsdcRawToUsd(strategy.stakeAmount, strategy.chainId);

  return (
    <section className="rounded-md border border-surface-line bg-surface-panel p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="font-display text-lg text-fg-primary">
              {formatStrategyClass(strategy.declaredClass)}
            </h2>
            <ChainBadge chainId={strategy.chainId} />
          </div>
          <p className="mt-1 flex items-center gap-2 text-xs">
            {explorer ? (
              <a
                href={explorer}
                target="_blank"
                rel="noreferrer"
                className="font-mono text-fg-muted hover:text-amber"
                title={strategy.id}
              >
                {formatAddress(strategy.id)} ↗
              </a>
            ) : (
              <span className="font-mono text-fg-muted" title={strategy.id}>
                {formatAddress(strategy.id)}
              </span>
            )}
            <CopyButton value={strategy.id} ariaLabel="Copy strategy address" />
          </p>
        </div>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-xs sm:grid-cols-3">
          <Field label="Operator">
            {operatorExplorer ? (
              <a
                href={operatorExplorer}
                target="_blank"
                rel="noreferrer"
                className="font-mono text-fg-primary hover:text-amber"
              >
                {formatAddress(strategy.operator)}
              </a>
            ) : (
              <span className="font-mono text-fg-primary">{formatAddress(strategy.operator)}</span>
            )}
          </Field>
          <Field label="Stake">
            <Numeric>{formatUsd(stake, { compact: true, cents: false })}</Numeric>
          </Field>
          <Field label="Trades attested">
            <Numeric>{strategy.totalAttestedTrades.toLocaleString()}</Numeric>
          </Field>
        </dl>
      </div>
    </section>
  );
}

function ReputationInputsPanel({ reputation }: { reputation: AuditPayload }): JSX.Element {
  const dominant = dominantComponent(reputation.components, reputation.weights);
  return (
    <section>
      <h2 className="mb-2 text-[12px] uppercase tracking-[0.16em] text-fg-muted">
        Reputation calculation inputs
      </h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <ComponentBreakdown
          label="Performance"
          weight={reputation.weights.performance}
          value={reputation.components.performance}
          signed
          highlighted={dominant === "performance"}
          hint="Cohort-relative Sharpe (7d/30d/90d)"
        />
        <ComponentBreakdown
          label="Risk"
          weight={reputation.weights.risk}
          value={reputation.components.risk}
          highlighted={dominant === "risk"}
          hint="1 − clip(MaxDD90d / 5000bps)"
        />
        <ComponentBreakdown
          label="Proof"
          weight={reputation.weights.proof}
          value={reputation.components.proof}
          highlighted={dominant === "proof"}
          hint="ValidProofs / TotalAttempts"
        />
        <ComponentBreakdown
          label="Stake"
          weight={reputation.weights.stake}
          value={reputation.components.stake}
          highlighted={dominant === "stake"}
          hint="log-normalized vs class max stake"
        />
        <ComponentBreakdown
          label="Age"
          weight={reputation.weights.age}
          value={reputation.components.age}
          highlighted={dominant === "age"}
          hint="√(trades_attested / 1000)"
        />
      </div>
    </section>
  );
}

function TradesTable({
  strategy,
  page,
  onPage,
  onVerify,
  isFetching,
}: {
  strategy: NonNullable<Awaited<ReturnType<typeof fetchStrategyAudit>>>;
  page: number;
  onPage: (_p: number) => void;
  onVerify: (_tx: string) => void;
  isFetching: boolean;
}): JSX.Element {
  const trades = strategy.trades;
  const totalKnown = strategy.totalAttestedTrades > 0;
  const totalPages = totalKnown
    ? Math.max(1, Math.ceil(strategy.totalAttestedTrades / PAGE_SIZE))
    : null;

  return (
    <section data-testid="audit-trades">
      <header className="mb-2 flex items-baseline justify-between">
        <h2 className="text-[12px] uppercase tracking-[0.16em] text-fg-muted">
          Attested trades — every record
        </h2>
        <span className="font-mono text-[12px] uppercase tracking-[0.12em] text-fg-muted">
          page {page + 1} / {totalPages ?? "—"}
          {isFetching ? " · loading…" : ""}
        </span>
      </header>

      {trades.length === 0 ? (
        <div className="rounded-md border border-surface-line bg-surface-panel p-8 text-center text-sm text-fg-muted">
          No attested trades on this page.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-md border border-surface-line bg-surface-panel">
          <table className="w-full text-sm">
            <thead className="border-b border-surface-line text-[12px] uppercase tracking-[0.16em] text-fg-muted">
              <tr>
                <th className="px-3 py-2.5 text-left font-normal">Timestamp (UTC)</th>
                <th className="px-3 py-2.5 text-center font-normal">Proof</th>
                <th className="px-3 py-2.5 text-left font-normal">Direction</th>
                <th className="px-3 py-2.5 text-left font-normal">Trade</th>
                <th className="px-3 py-2.5 text-left font-normal">Proof hash</th>
                <th className="px-3 py-2.5 text-right font-normal">Tx</th>
                <th className="px-3 py-2.5" aria-hidden />
              </tr>
            </thead>
            <tbody>
              {trades.map((trade) => (
                <AuditTradeRow
                  key={trade.id}
                  trade={trade}
                  chainId={strategy.chainId}
                  onVerify={onVerify}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-3 flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={() => onPage(Math.max(0, page - 1))}
          disabled={page === 0}
          className="rounded-sm border border-surface-line px-3 py-1 font-mono text-xs text-fg-secondary hover:border-amber/40 hover:text-fg-primary disabled:opacity-40"
        >
          ← Prev
        </button>
        <button
          type="button"
          onClick={() => onPage(page + 1)}
          disabled={trades.length < PAGE_SIZE}
          className="rounded-sm border border-surface-line px-3 py-1 font-mono text-xs text-fg-secondary hover:border-amber/40 hover:text-fg-primary disabled:opacity-40"
        >
          Next →
        </button>
      </div>
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }): JSX.Element {
  return (
    <div>
      <dt className="text-[12px] uppercase tracking-[0.16em] text-fg-muted">{label}</dt>
      <dd className="mt-0.5 font-mono">{children}</dd>
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

function Skeleton(): JSX.Element {
  return (
    <div className="flex flex-col gap-6" aria-busy="true" aria-live="polite">
      <div className="h-32 rounded-md border border-surface-line bg-surface-panel" />
      <div className="h-72 rounded-md border border-surface-line bg-surface-panel" />
    </div>
  );
}

function NotFound({ id }: { id: string }): JSX.Element {
  return (
    <div className="rounded-md border border-surface-line bg-surface-panel p-6 text-sm">
      <p className="text-fg-primary">Strategy not indexed.</p>
      <p className="mt-1 font-mono text-xs text-fg-muted">{id}</p>
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
