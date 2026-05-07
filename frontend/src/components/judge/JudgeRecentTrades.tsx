/**
 * Judge — recent trades panel.
 *
 * Pulls the 12 most-recent on-chain `Trade` rows from the subgraph
 * and surfaces them as a flat table with a Kitescan deeplink per row.
 * Per `TODO.md` line 371 (judging-criteria audit, criterion C): a
 * judge needs to be able to verify the system end-to-end without
 * the VPS up. Each tx hash deep-links into the explorer; the proof
 * shield is the "acknowledged" ZK visibility tier from DESIGN §12.
 */

"use client";

import { useQuery } from "@tanstack/react-query";

import { ChainBadge } from "@/components/atoms/ChainBadge";
import { ProofBadge } from "@/components/atoms/ProofBadge";
import { fetchLandingStats, type LandingStats } from "@/lib/goldsky";
import { explorerTxUrl, formatStrategyClass, formatTimestamp } from "@/lib/format";

export function JudgeRecentTrades(): JSX.Element {
  const query = useQuery<LandingStats, Error>({
    queryKey: ["landing-stats"],
    queryFn: ({ signal }) => fetchLandingStats(signal),
    refetchInterval: (q) => (q.state.error ? false : 30_000),
    staleTime: 15_000,
    retry: false,
  });

  return (
    <section aria-labelledby="judge-recent">
      <div className="mb-3 flex items-baseline justify-between">
        <h2
          id="judge-recent"
          className="text-[12px] uppercase tracking-[0.16em] text-fg-muted"
        >
          Recent attested trades
        </h2>
        <span className="font-mono text-[12px] uppercase tracking-[0.16em] text-fg-muted">
          {query.data ? `${query.data.recentTrades.length} rows` : "loading"}
        </span>
      </div>
      <div
        data-testid="judge-recent-trades"
        className="overflow-hidden rounded-md border border-surface-line bg-surface-panel"
      >
        <table className="w-full text-sm">
          <thead className="border-b border-surface-line text-[12px] uppercase tracking-[0.16em] text-fg-muted">
            <tr>
              <th className="px-3 py-2.5 text-left font-normal">When</th>
              <th className="px-3 py-2.5 text-left font-normal">Class</th>
              <th className="px-3 py-2.5 text-left font-normal">Chain</th>
              <th className="px-3 py-2.5 text-left font-normal">Proof</th>
              <th className="px-3 py-2.5 text-right font-normal">Tx</th>
            </tr>
          </thead>
          <tbody>
            {query.data && query.data.recentTrades.length > 0 ? (
              query.data.recentTrades.map((row) => {
                const ts = Number.parseInt(row.timestamp, 10);
                const explorer = explorerTxUrl(row.strategy.chainId, row.txHash);
                return (
                  <tr key={row.id} className="border-b border-surface-line last:border-b-0">
                    <td className="px-3 py-2 font-mono text-[12px] text-fg-secondary">
                      {Number.isFinite(ts) ? formatTimestamp(ts) : "—"}
                    </td>
                    <td className="px-3 py-2 text-fg-primary">
                      {formatStrategyClass(row.strategy.declaredClass)}
                    </td>
                    <td className="px-3 py-2">
                      <ChainBadge chainId={row.strategy.chainId} />
                    </td>
                    <td className="px-3 py-2">
                      <ProofBadge state={row.proofValid ? "valid" : "failed"} showLabel />
                    </td>
                    <td className="px-3 py-2 text-right">
                      {explorer ? (
                        <a
                          href={explorer}
                          target="_blank"
                          rel="noreferrer"
                          className="font-mono text-[12px] text-amber hover:underline"
                        >
                          {row.txHash.slice(0, 10)}… ↗
                        </a>
                      ) : (
                        <span className="font-mono text-[12px] text-fg-muted">—</span>
                      )}
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td
                  colSpan={5}
                  className="px-3 py-6 text-center text-[12px] text-fg-muted"
                >
                  {query.isError
                    ? "Subgraph unreachable. Run scripts/e2e-scenario.sh locally to populate."
                    : "Awaiting first attested trade."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
