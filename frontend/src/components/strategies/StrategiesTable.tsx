/**
 * Strategies directory table. DESIGN.md §9.4 — sortable on every
 * column, filterable by class/chain/reputation. Bloomberg-density
 * inside the component, calm spacing around it.
 *
 * Data comes from Goldsky (`fetchStrategies`); when the subgraph isn't
 * reachable callers render an empty state above this component.
 */

"use client";

import { useMemo, useState } from "react";

import { ChainBadge } from "@/components/atoms/ChainBadge";
import { Numeric, toneFor } from "@/components/atoms/Numeric";
import { ArrowDownIcon, ArrowUpIcon } from "@/components/icon";
import { cn } from "@/lib/cn";
import {
  classSlugToHash,
  explorerAddressUrl,
  formatAddress,
  formatBpsAsPct,
  formatStrategyClass,
  formatUsd,
} from "@/lib/format";
import type { StrategyDirectoryRow } from "@/lib/goldsky";

type SortKey =
  | "currentReputation"
  | "totalRealizedPnL"
  | "feeRateBps"
  | "stakeAmount"
  | "totalAttestedTrades"
  | "maxDrawdownBps";

type SortDir = "asc" | "desc";

const COLUMNS: Array<{ key: SortKey | "name" | "class" | "chain"; label: string; align: "left" | "right"; sortable: boolean }> = [
  { key: "name", label: "Strategy", align: "left", sortable: false },
  { key: "class", label: "Class", align: "left", sortable: false },
  { key: "chain", label: "Chain", align: "left", sortable: false },
  { key: "currentReputation", label: "Reputation", align: "right", sortable: true },
  { key: "totalRealizedPnL", label: "Realized P&L", align: "right", sortable: true },
  { key: "feeRateBps", label: "Fee", align: "right", sortable: true },
  { key: "stakeAmount", label: "Stake", align: "right", sortable: true },
  { key: "totalAttestedTrades", label: "Trades", align: "right", sortable: true },
  { key: "maxDrawdownBps", label: "Max DD", align: "right", sortable: true },
];

export type StrategiesTableProps = {
  rows: StrategyDirectoryRow[];
  classFilter: string | null;
  chainFilter: number | null;
};

export function StrategiesTable({ rows, classFilter, chainFilter }: StrategiesTableProps): JSX.Element {
  const [sortKey, setSortKey] = useState<SortKey>("currentReputation");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const filtered = useMemo(() => {
    // Subgraph emits `declaredClass` as the bytes32 hash; filter chips
    // emit the human slug. Compare on the hash.
    const classHash = classFilter ? classSlugToHash(classFilter) : null;
    return rows.filter((r) => {
      if (classHash && r.declaredClass.toLowerCase() !== classHash) return false;
      if (chainFilter != null && r.chainId !== chainFilter) return false;
      return true;
    });
  }, [rows, classFilter, chainFilter]);

  const sorted = useMemo(() => {
    const arr = [...filtered];
    arr.sort((a, b) => {
      const av = readSortValue(a, sortKey);
      const bv = readSortValue(b, sortKey);
      if (av === bv) return 0;
      const cmp = av < bv ? -1 : 1;
      return sortDir === "asc" ? cmp : -cmp;
    });
    return arr;
  }, [filtered, sortKey, sortDir]);

  function toggleSort(key: SortKey): void {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  if (sorted.length === 0) {
    return (
      <div className="rounded-md border border-surface-line bg-surface-panel p-8 text-center text-sm text-fg-muted">
        No strategies match the current filter.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-md border border-surface-line bg-surface-panel">
      <table className="w-full text-sm">
        <thead className="border-b border-surface-line text-[10px] uppercase tracking-[0.16em] text-fg-muted">
          <tr>
            {COLUMNS.map((col) => (
              <th
                key={col.key}
                scope="col"
                className={cn(
                  "px-3 py-2.5 font-normal",
                  col.align === "right" ? "text-right" : "text-left",
                )}
              >
                {col.sortable ? (
                  <button
                    type="button"
                    onClick={() => toggleSort(col.key as SortKey)}
                    className={cn(
                      "inline-flex items-center gap-1 hover:text-fg-primary",
                      col.align === "right" && "flex-row-reverse",
                      sortKey === col.key && "text-amber",
                    )}
                  >
                    <span>{col.label}</span>
                    {sortKey === col.key ? (
                      sortDir === "desc" ? (
                        <ArrowDownIcon className="h-3 w-3" />
                      ) : (
                        <ArrowUpIcon className="h-3 w-3" />
                      )
                    ) : null}
                  </button>
                ) : (
                  col.label
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <Row key={row.id} row={row} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Row({ row }: { row: StrategyDirectoryRow }): JSX.Element {
  const reputation = readReputation(row);
  const pnl = readPnL(row);
  const stake = readStake(row);
  const drawdown = row.maxDrawdownBps;

  // /strategies/[id] is a Phase 4 page; until then the strategy
  // address links out to OKLink so judges + auditors can still inspect.
  const detailHref = explorerAddressUrl(row.chainId, row.id);

  return (
    <tr className="border-b border-surface-line last:border-b-0 hover:bg-surface-elev">
      <td className="px-3 py-2.5 text-fg-primary">
        {detailHref ? (
          <a
            href={detailHref}
            target="_blank"
            rel="noreferrer"
            className="hover:text-amber"
          >
            {operatorLabel(row)}
          </a>
        ) : (
          operatorLabel(row)
        )}
      </td>
      <td className="px-3 py-2.5 text-fg-secondary">{formatStrategyClass(row.declaredClass)}</td>
      <td className="px-3 py-2.5">
        <ChainBadge chainId={row.chainId} />
      </td>
      <td className="px-3 py-2.5 text-right">
        <Numeric tone={reputation > 50 ? "positive" : reputation > 0 ? "default" : "muted"} align="right">
          {reputation.toFixed(1)}
        </Numeric>
      </td>
      <td className="px-3 py-2.5 text-right">
        <Numeric tone={toneFor(pnl)} align="right">
          {formatUsd(pnl, { compact: true })}
        </Numeric>
      </td>
      <td className="px-3 py-2.5 text-right">
        <Numeric tone="muted" align="right">
          {formatBpsAsPct(row.feeRateBps)}
        </Numeric>
      </td>
      <td className="px-3 py-2.5 text-right">
        <Numeric align="right">{formatUsd(stake, { compact: true, cents: false })}</Numeric>
      </td>
      <td className="px-3 py-2.5 text-right">
        <Numeric align="right">{row.totalAttestedTrades}</Numeric>
      </td>
      <td className="px-3 py-2.5 text-right">
        <Numeric tone={drawdown > 0 ? "negative" : "muted"} align="right">
          {drawdown > 0 ? `−${formatBpsAsPct(drawdown)}` : "—"}
        </Numeric>
      </td>
    </tr>
  );
}

function operatorLabel(row: StrategyDirectoryRow): string {
  // Strategies don't carry display names in the subgraph yet — use the
  // class + operator-tail until /strategies/[id] adds a manifest header.
  const cls = formatStrategyClass(row.declaredClass);
  return `${cls} · ${formatAddress(row.id)}`;
}

function readReputation(row: StrategyDirectoryRow): number {
  // Subgraph stores reputation as a fixed-point integer (BigInt string).
  // Phase 1 reputation is in the 0–100 range; safe to coerce via Number.
  return Number(row.currentReputation) / 1e18 || Number(row.currentReputation) || 0;
}

function readPnL(row: StrategyDirectoryRow): number {
  return Number(row.totalRealizedPnL);
}

function readStake(row: StrategyDirectoryRow): number {
  return Number(row.stakeAmount);
}

function readSortValue(row: StrategyDirectoryRow, key: SortKey): number {
  switch (key) {
    case "currentReputation":
      return readReputation(row);
    case "totalRealizedPnL":
      return readPnL(row);
    case "feeRateBps":
      return row.feeRateBps;
    case "stakeAmount":
      return readStake(row);
    case "totalAttestedTrades":
      return row.totalAttestedTrades;
    case "maxDrawdownBps":
      return row.maxDrawdownBps;
  }
}

