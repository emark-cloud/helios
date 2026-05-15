/**
 * Cumulative P&L curve — derived from `NAVSnapshot` (P&L = NAV − HWM₀).
 * Reuses the same hand-rolled SVG shell as `NavTimeline` (separate
 * component because the framing question is different: P&L answers
 * "how much value has the strategy created", NAV answers "what's it
 * worth now"). Drawdown shaded under the line per `DESIGN.md §11`.
 */

"use client";

import { useMemo } from "react";

import { Numeric, toneFor } from "@/components/atoms/Numeric";
import { formatPct, formatTimestamp, formatUsd, mUsdcRawToUsd } from "@/lib/format";
import type { NavSnapshotRow } from "@/lib/goldsky";

type Point = { ts: number; pnl: number; drawdownPct: number };

export function PnLCurve({
  snapshots,
  chainId,
}: {
  snapshots: NavSnapshotRow[];
  chainId: number;
}): JSX.Element {
  const points = useMemo(() => buildPoints(snapshots, chainId), [snapshots, chainId]);

  if (points.length < 2) {
    return (
      <section data-testid="pnl-curve">
        <h2 className="mb-2 text-[12px] uppercase tracking-[0.16em] text-fg-muted">
          Cumulative P&amp;L
        </h2>
        <div className="rounded-md border border-surface-line bg-surface-panel p-8 text-center text-sm text-fg-muted">
          P&amp;L derives from NAV snapshots; the strategy needs at
          least two snapshots before a curve can render.
        </div>
      </section>
    );
  }

  const last = points[points.length - 1]!;
  const headlinePct = last.pnl !== 0 && points[0]!.pnl !== 0
    ? ((last.pnl - points[0]!.pnl) / Math.abs(points[0]!.pnl || 1)) * 100
    : 0;

  return (
    <section data-testid="pnl-curve">
      <h2 className="mb-2 text-[12px] uppercase tracking-[0.16em] text-fg-muted">
        Cumulative P&amp;L
      </h2>
      <div className="rounded-md border border-surface-line bg-surface-panel p-4">
        <div className="mb-3 flex items-baseline justify-between gap-3">
          <div>
            <p className="text-[12px] uppercase tracking-[0.16em] text-fg-muted">Cumulative</p>
            <Numeric tone={toneFor(last.pnl)} className="font-mono text-2xl">
              {last.pnl >= 0 ? "+" : ""}
              {formatUsd(last.pnl, { compact: true, cents: false })}
            </Numeric>
          </div>
          <div className="text-right">
            <p className="text-[12px] uppercase tracking-[0.16em] text-fg-muted">
              Recent change
            </p>
            <Numeric tone={toneFor(headlinePct)} className="font-mono text-lg">
              {formatPct(headlinePct, { signed: true })}
            </Numeric>
          </div>
        </div>
        <Chart points={points} />
      </div>
    </section>
  );
}

function buildPoints(snapshots: NavSnapshotRow[], chainId: number): Point[] {
  if (snapshots.length === 0) return [];
  const ordered = [...snapshots].sort((a, b) => Number(a.timestamp) - Number(b.timestamp));
  const baseNav = mUsdcRawToUsd(ordered[0]!.totalNAV, chainId);
  let runningHwm = baseNav;
  return ordered.map((s) => {
    const nav = mUsdcRawToUsd(s.totalNAV, chainId);
    runningHwm = Math.max(runningHwm, nav);
    const drawdown = runningHwm > 0 ? ((runningHwm - nav) / runningHwm) * 100 : 0;
    return { ts: Number(s.timestamp), pnl: nav - baseNav, drawdownPct: drawdown };
  });
}

function Chart({ points }: { points: Point[] }): JSX.Element {
  const width = 760;
  const height = 200;
  const padX = 32;
  const padTop = 8;
  const padBottom = 24;

  const xs = points.map((p) => p.ts);
  const pnls = points.map((p) => p.pnl);
  const yMin = Math.min(...pnls, 0) * 1.05;
  const yMaxRaw = Math.max(...pnls, 0) * 1.05;
  const yMax = yMaxRaw === yMin ? yMin + 1 : yMaxRaw;

  const xScale = (x: number): number =>
    padX + ((x - xs[0]!) / Math.max(1, xs[xs.length - 1]! - xs[0]!)) * (width - padX * 2);
  const yScale = (y: number): number =>
    padTop + ((yMax - y) / (yMax - yMin)) * (height - padTop - padBottom);

  const linePath = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${xScale(p.ts).toFixed(1)} ${yScale(p.pnl).toFixed(1)}`)
    .join(" ");

  // Drawdown intensity: shade the line a notch toward red where
  // drawdown > 5%. Cheaper than splitting paths — single overlay.
  const ddPath = points
    .map((p, i) => {
      if (p.drawdownPct < 5) return null;
      const x = xScale(p.ts);
      const y = yScale(p.pnl);
      return `${i === 0 || points[i - 1]!.drawdownPct < 5 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .filter(Boolean)
    .join(" ");

  // Zero baseline guide.
  const zeroY = yMin <= 0 && yMax >= 0 ? yScale(0) : null;

  return (
    <svg
      role="img"
      aria-label="Cumulative P&L"
      viewBox={`0 0 ${width} ${height}`}
      className="block w-full"
      style={{ maxHeight: 240 }}
    >
      {zeroY != null ? (
        <line
          x1={padX}
          x2={width - padX}
          y1={zeroY}
          y2={zeroY}
          stroke="var(--surface-line-strong)"
          strokeWidth={0.75}
          strokeDasharray="2 4"
        />
      ) : null}

      <text
        x={padX - 4}
        y={yScale(yMax) + 8}
        textAnchor="end"
        className="fill-fg-muted font-mono"
        fontSize={9}
      >
        {formatUsd(yMax, { compact: true, cents: false })}
      </text>
      <text
        x={padX - 4}
        y={yScale(yMin) - 2}
        textAnchor="end"
        className="fill-fg-muted font-mono"
        fontSize={9}
      >
        {formatUsd(yMin, { compact: true, cents: false })}
      </text>

      <path d={linePath} fill="none" stroke="var(--accent-amber)" strokeWidth={1.5} />
      {ddPath ? (
        <path d={ddPath} fill="none" stroke="var(--signal-negative)" strokeWidth={2} opacity={0.7} />
      ) : null}

      <text
        x={padX}
        y={height - 6}
        className="fill-fg-muted font-mono"
        fontSize={9}
      >
        {formatTimestamp(points[0]!.ts)}
      </text>
      <text
        x={width - padX}
        y={height - 6}
        textAnchor="end"
        className="fill-fg-muted font-mono"
        fontSize={9}
      >
        {formatTimestamp(points[points.length - 1]!.ts)}
      </text>
    </svg>
  );
}
