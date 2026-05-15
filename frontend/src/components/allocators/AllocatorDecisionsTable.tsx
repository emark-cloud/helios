/**
 * Recent decisions table for `/allocators/[name]`. Reads
 * `AllocatorDecision` from the subgraph (WS5.B). One row per allocator
 * action: ALLOCATE | DEFUND | REBALANCE_INCREASE | REBALANCE_DECREASE.
 */

import { Numeric, toneFor } from "@/components/atoms/Numeric";
import {
  explorerTxUrl,
  formatAddress,
  formatRelative,
  formatStrategyClass,
  formatUsd,
  mUsdcRawToUsd,
} from "@/lib/format";
import type { AllocatorDecisionRow } from "@/lib/goldsky";

export type AllocatorDecisionsTableProps = {
  decisions: ReadonlyArray<AllocatorDecisionRow>;
  /// Source chain — every decision lands on the same chain as the
  /// allocator vault, so we surface explorer links uniformly.
  chainId: number;
};

export function AllocatorDecisionsTable({
  decisions,
  chainId,
}: AllocatorDecisionsTableProps): JSX.Element {
  if (decisions.length === 0) {
    return (
      <div className="rounded-md border border-surface-line bg-surface-panel p-8 text-center text-sm text-fg-muted">
        No decisions on chain yet. The first allocate will land here once
        the allocator service starts trading.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-md border border-surface-line bg-surface-panel">
      <table className="w-full text-sm">
        <thead className="border-b border-surface-line text-[12px] uppercase tracking-[0.16em] text-fg-muted">
          <tr>
            <th scope="col" className="px-3 py-2.5 text-left font-normal">
              When
            </th>
            <th scope="col" className="px-3 py-2.5 text-left font-normal">
              Kind
            </th>
            <th scope="col" className="px-3 py-2.5 text-left font-normal">
              Strategy
            </th>
            <th scope="col" className="px-3 py-2.5 text-left font-normal">
              User
            </th>
            <th scope="col" className="px-3 py-2.5 text-right font-normal">
              Amount
            </th>
            <th scope="col" className="px-3 py-2.5 text-left font-normal">
              Reason
            </th>
          </tr>
        </thead>
        <tbody>
          {decisions.map((d) => {
            const ts = Number(d.timestamp);
            // Decision capital is denominated in the target strategy's
            // chain mUSDC (Kite 18-dec / Base+Arb 6-dec). Kite fallback
            // when the decision has no joined strategy.
            const amount = mUsdcRawToUsd(d.amount, d.strategy?.chainId ?? 2368);
            const txHref = explorerTxUrl(chainId, d.txHash);
            return (
              <tr key={d.id} className="border-b border-surface-line last:border-b-0">
                <td className="px-3 py-2.5 text-fg-secondary">
                  {txHref ? (
                    <a href={txHref} target="_blank" rel="noreferrer" className="hover:text-amber">
                      {formatRelative(ts)}
                    </a>
                  ) : (
                    formatRelative(ts)
                  )}
                </td>
                <td className="px-3 py-2.5">
                  <KindChip kind={d.kind} />
                </td>
                <td className="px-3 py-2.5 text-fg-secondary">
                  {d.strategy ? (
                    <span className="font-mono text-xs">
                      {formatStrategyClass(d.strategy.declaredClass)} ·{" "}
                      {formatAddress(d.strategy.id)}
                    </span>
                  ) : (
                    <span className="text-fg-muted">—</span>
                  )}
                </td>
                <td className="px-3 py-2.5 font-mono text-xs text-fg-secondary">
                  {d.user ? formatAddress(d.user.id) : "—"}
                </td>
                <td className="px-3 py-2.5 text-right">
                  <Numeric tone={toneFor(amount * (d.kind.startsWith("DEFUND") ? -1 : 1))}>
                    {formatUsd(amount, { compact: true, cents: false })}
                  </Numeric>
                </td>
                <td className="px-3 py-2.5 text-xs text-fg-muted">{d.reason ?? "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function KindChip({ kind }: { kind: string }): JSX.Element {
  const tone =
    kind === "ALLOCATE" || kind === "REBALANCE_INCREASE"
      ? "border-signal-positive/40 text-signal-positive"
      : kind === "DEFUND" || kind === "REBALANCE_DECREASE"
        ? "border-signal-negative-dim text-signal-negative"
        : "border-surface-line text-fg-secondary";
  return (
    <span
      className={`rounded-sm border px-1.5 py-0.5 font-mono text-[12px] uppercase tracking-[0.12em] ${tone}`}
    >
      {kind}
    </span>
  );
}

