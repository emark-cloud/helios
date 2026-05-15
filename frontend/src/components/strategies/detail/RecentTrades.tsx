/**
 * Recent-trades table for `/strategies/[id]`. Last 20 attestations.
 *
 * Per `DESIGN.md §12` shield treatment: each row carries a small
 * shield with proof status; the audit page (`/audit/[strategy]`)
 * shows the celebrated 32px treatment. Click on the proof shield
 * deep-links into the audit page focused on that tx hash.
 */

import Link from "next/link";
import type { Route } from "next";

import { Numeric } from "@/components/atoms/Numeric";
import { ProofBadge } from "@/components/atoms/ProofBadge";
import { decodeTokenAmount, formatAssetSymbol } from "@/lib/addresses";
import {
  explorerTxUrl,
  formatAddress,
  formatRelative,
  formatUsd,
} from "@/lib/format";
import type { StrategyTradeRow } from "@/lib/goldsky";

export function RecentTrades({
  strategyId,
  chainId,
  trades,
}: {
  strategyId: string;
  chainId: number;
  trades: StrategyTradeRow[];
}): JSX.Element {
  return (
    <section data-testid="recent-trades">
      <header className="mb-2 flex items-baseline justify-between">
        <h2 className="text-[12px] uppercase tracking-[0.16em] text-fg-muted">
          Recent trades
        </h2>
        <Link
          href={`/audit/strategy/${strategyId.toLowerCase()}` as Route}
          className="font-mono text-[12px] uppercase tracking-[0.12em] text-fg-muted hover:text-amber"
        >
          Full audit →
        </Link>
      </header>

      {trades.length === 0 ? (
        <div className="rounded-md border border-surface-line bg-surface-panel p-6 text-center text-sm text-fg-muted">
          No attested trades yet. Trades arrive once the strategy
          executes its first <code className="font-mono">executeWithProof</code>.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-md border border-surface-line bg-surface-panel">
          <table className="w-full text-sm">
            <thead className="border-b border-surface-line text-[12px] uppercase tracking-[0.16em] text-fg-muted">
              <tr>
                <th className="px-3 py-2.5 text-left font-normal">When</th>
                <th className="px-3 py-2.5 text-left font-normal">Direction</th>
                <th className="px-3 py-2.5 text-left font-normal">Asset in</th>
                <th className="px-3 py-2.5 text-left font-normal">Asset out</th>
                <th className="px-3 py-2.5 text-right font-normal">Size</th>
                <th className="px-3 py-2.5 text-right font-normal">Min out</th>
                <th className="px-3 py-2.5 text-center font-normal">Proof</th>
                <th className="px-3 py-2.5 text-right font-normal">Tx</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((trade) => (
                <Row key={trade.id} chainId={chainId} trade={trade} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function Row({ chainId, trade }: { chainId: number; trade: StrategyTradeRow }): JSX.Element {
  const explorer = explorerTxUrl(chainId, trade.txHash);
  const ts = Number(trade.timestamp);
  const sizeIn = decodeTokenAmount(trade.amountIn, trade.assetIn, chainId);
  const minOut = decodeTokenAmount(trade.minAmountOut, trade.assetOut, chainId);

  return (
    <tr className="border-b border-surface-line last:border-b-0 hover:bg-surface-elev">
      <td className="px-3 py-2.5">
        <div className="text-fg-primary">{formatRelative(ts)}</div>
        <div className="font-mono text-[12px] text-fg-muted">
          block {trade.blockWindowEnd}
        </div>
      </td>
      <td className="px-3 py-2.5 text-fg-secondary">
        {directionLabel(trade.direction)}
      </td>
      <td className="px-3 py-2.5 font-mono text-xs text-fg-secondary" title={trade.assetIn}>
        {formatAssetSymbol(trade.assetIn, chainId)}
      </td>
      <td className="px-3 py-2.5 font-mono text-xs text-fg-secondary" title={trade.assetOut}>
        {formatAssetSymbol(trade.assetOut, chainId)}
      </td>
      <td className="px-3 py-2.5 text-right">
        <Numeric align="right">{formatAmount(sizeIn)}</Numeric>
      </td>
      <td className="px-3 py-2.5 text-right">
        <Numeric align="right" tone="muted">
          {formatAmount(minOut)}
        </Numeric>
      </td>
      <td className="px-3 py-2.5 text-center">
        <ProofBadge state={trade.proofValid ? "valid" : "failed"} />
      </td>
      <td className="px-3 py-2.5 text-right">
        {explorer ? (
          <a
            href={explorer}
            target="_blank"
            rel="noreferrer"
            className="font-mono text-xs text-fg-muted hover:text-amber"
            title={trade.txHash}
          >
            {formatAddress(trade.txHash)}
          </a>
        ) : (
          <span className="font-mono text-xs text-fg-muted" title={trade.txHash}>
            {formatAddress(trade.txHash)}
          </span>
        )}
      </td>
    </tr>
  );
}

/** Trade.direction is a uint8: 0 = swap, 1 = rotate-to-yield, 2 = rotate-to-cash. */
function directionLabel(direction: number): string {
  if (direction === 0) return "Swap";
  if (direction === 1) return "Yield in";
  if (direction === 2) return "Yield out";
  return `op ${direction}`;
}

/// Render a decoded trade amount. USD-pegged assets get the `$`
/// treatment; other universe tokens render as a token quantity with
/// their symbol (no price oracle on the frontend, so a USD figure
/// would be a fabrication). Unknown tokens → "—".
function formatAmount(
  decoded: { amount: number; symbol: string; isUsd: boolean } | null,
): string {
  if (decoded == null) return "—";
  if (decoded.isUsd) return formatUsd(decoded.amount, { compact: true, cents: false });
  const qty = decoded.amount.toLocaleString("en-US", {
    maximumFractionDigits: decoded.amount < 1 ? 6 : 4,
  });
  return `${qty} ${decoded.symbol}`;
}
