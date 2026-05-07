/**
 * One trade row on `/audit/strategy/[id]`. Per `DESIGN.md §12`
 * celebrated tier: 32×32 shield, full-length proof hash, "verify
 * yourself" CTA on the row.
 *
 * Click row → expand inline. Expansion shows the public-input
 * vector (decoded), the calldata hex, and the same Verify CTA.
 */

"use client";

import { useState } from "react";

import { Numeric } from "@/components/atoms/Numeric";
import { ChevronDown } from "./icons";
import { ShieldIcon } from "@/components/icon";
import { cn } from "@/lib/cn";
import {
  explorerTxUrl,
  formatAddress,
  formatTimestamp,
  formatUsd,
} from "@/lib/format";
import type { AuditTradeRow as AuditTradeRowType } from "@/lib/goldsky";

export function AuditTradeRow({
  trade,
  chainId,
  onVerify,
}: {
  trade: AuditTradeRowType;
  chainId: number;
  onVerify: (_txHash: string) => void;
}): JSX.Element {
  const [expanded, setExpanded] = useState(false);
  const explorer = explorerTxUrl(chainId, trade.txHash);
  const ts = Number(trade.timestamp);
  const isoTs = new Date(ts * 1000).toISOString();
  const sizeUsd = decodeAmount(trade.amountIn);

  const proofState: "valid" | "failed" = trade.proofValid ? "valid" : "failed";

  return (
    <>
      <tr
        className={cn(
          "border-b border-surface-line last:border-b-0 cursor-pointer hover:bg-surface-elev",
          expanded && "bg-surface-elev",
        )}
        onClick={() => setExpanded((v) => !v)}
      >
        <td className="px-3 py-3 align-top">
          <div className="font-mono text-xs text-fg-primary" title={isoTs}>
            {formatTimestamp(ts)}
          </div>
          <div className="font-mono text-[10px] text-fg-muted">{isoTs.slice(11, 19)}Z</div>
        </td>
        <td className="px-3 py-3 align-top">
          <ShieldTreatment state={proofState} />
        </td>
        <td className="px-3 py-3 align-top text-fg-secondary">{directionLabel(trade.direction)}</td>
        <td className="px-3 py-3 align-top">
          <Numeric>{sizeUsd != null ? formatUsd(sizeUsd, { compact: true, cents: false }) : "—"}</Numeric>
          <div className="font-mono text-[10px] text-fg-muted">
            {formatAddress(trade.assetIn)} → {formatAddress(trade.assetOut)}
          </div>
        </td>
        <td className="px-3 py-3 align-top">
          <code className="break-all font-mono text-[11px] text-fg-secondary">{trade.id}</code>
        </td>
        <td className="px-3 py-3 align-top text-right">
          {explorer ? (
            <a
              href={explorer}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
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
        <td className="px-3 py-3 align-top text-right">
          <ChevronDown className={cn("inline h-4 w-4 text-fg-muted transition-transform motion-reduce:transition-none", expanded && "rotate-180")} />
        </td>
      </tr>
      {expanded ? (
        <tr className="border-b border-surface-line bg-surface-base/40 last:border-b-0">
          <td colSpan={7} className="px-4 py-4">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <p className="text-[10px] uppercase tracking-[0.16em] text-fg-muted">
                  Public inputs
                </p>
                <dl className="mt-1.5 space-y-0.5 font-mono text-[11px] text-fg-secondary">
                  <Pair label="declaredClass" value={trade.declaredClass} />
                  <Pair label="assetIn" value={trade.assetIn} />
                  <Pair label="assetOut" value={trade.assetOut} />
                  <Pair label="amountIn" value={trade.amountIn} />
                  <Pair label="minAmountOut" value={trade.minAmountOut} />
                  <Pair label="direction" value={String(trade.direction)} />
                  <Pair label="blockWindowStart" value={trade.blockWindowStart} />
                  <Pair label="blockWindowEnd" value={trade.blockWindowEnd} />
                  <Pair label="block" value={trade.blockNumber} />
                </dl>
              </div>
              <div className="flex flex-col items-start gap-3">
                <div className="w-full">
                  <p className="text-[10px] uppercase tracking-[0.16em] text-fg-muted">
                    Verifier result
                  </p>
                  <p
                    className={cn(
                      "mt-1.5 font-mono text-sm",
                      proofState === "valid" ? "text-signal-positive" : "text-signal-negative",
                    )}
                  >
                    {proofState === "valid" ? "✓ verified by Groth16" : "✗ verification failed"}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onVerify(trade.txHash);
                  }}
                  className="rounded-sm border border-amber/40 px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.12em] text-amber hover:border-amber/80"
                >
                  Verify yourself →
                </button>
              </div>
            </div>
          </td>
        </tr>
      ) : null}
    </>
  );
}

function ShieldTreatment({ state }: { state: "valid" | "failed" }): JSX.Element {
  const tone = state === "valid" ? "text-signal-positive" : "text-signal-negative";
  const label = state === "valid" ? "Groth16 verified" : "Proof failed";
  return (
    <div className="flex flex-col items-center gap-1" aria-label={label} title={label}>
      <ShieldIcon filled={state === "valid"} className={cn("h-8 w-8", tone)} />
      <span className={cn("font-mono text-[9px] uppercase tracking-[0.12em]", tone)}>
        {state === "valid" ? "Verified" : "Failed"}
      </span>
    </div>
  );
}

function Pair({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className="flex items-baseline gap-2">
      <dt className="w-32 shrink-0 text-fg-muted">{label}</dt>
      <dd className="flex-1 break-all" title={value}>
        {value}
      </dd>
    </div>
  );
}

function directionLabel(direction: number): string {
  if (direction === 0) return "Swap";
  if (direction === 1) return "Yield in";
  if (direction === 2) return "Yield out";
  return `op ${direction}`;
}

function decodeAmount(raw: string): number | null {
  const n = Number(raw);
  if (!Number.isFinite(n) || n === 0) return 0;
  if (n < 1e15) return n / 1e6;
  return null;
}
