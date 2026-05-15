/**
 * NAV timeline + drawdown envelope. Hand-rolled SVG line chart — no
 * recharts/d3 to keep the frontend bundle lean (per `DESIGN.md §14.5`
 * and the consistent rule against incidental deps).
 *
 * The line is the NAV; the shaded envelope underneath shows
 * `(HWM − NAV) / HWM` so a viewer reads drawdown without consulting a
 * separate chart. HWM is the running maximum of NAV — a cheap
 * pessimal-cumulative-max, not a separate stored series.
 */

"use client";

import { useMemo, useState } from "react";

import { Numeric, toneFor } from "@/components/atoms/Numeric";
import { cn } from "@/lib/cn";
import { formatPct, formatTimestamp, formatUsd, mUsdcRawToUsd } from "@/lib/format";
import type { NavSnapshotRow } from "@/lib/goldsky";

type Window = "24h" | "7d" | "30d";

export function NavTimeline({
  snapshots,
  chainId,
}: {
  snapshots: NavSnapshotRow[];
  chainId: number;
}): JSX.Element {
  const [windowSel, setWindow] = useState<Window>("24h");

  const points = useMemo(
    () => buildPoints(snapshots, windowSel, chainId),
    [snapshots, windowSel, chainId],
  );

  if (points.length < 2) {
    return (
      <section data-testid="nav-timeline">
        <SectionHeader window={windowSel} onWindow={setWindow} />
        <div className="rounded-md border border-surface-line bg-surface-panel p-8 text-center text-sm text-fg-muted">
          Not enough NAV snapshots to draw the timeline. The reference
          oracle posts on a 1-minute cadence; come back in a few minutes.
        </div>
      </section>
    );
  }

  const headlinePnL = points[points.length - 1]!.nav - points[0]!.nav;
  const headlinePnLPct = points[0]!.nav > 0 ? (headlinePnL / points[0]!.nav) * 100 : 0;

  return (
    <section data-testid="nav-timeline">
      <SectionHeader window={windowSel} onWindow={setWindow} />
      <div className="rounded-md border border-surface-line bg-surface-panel p-4">
        <div className="mb-3 flex items-baseline justify-between gap-3">
          <div>
            <p className="text-[12px] uppercase tracking-[0.16em] text-fg-muted">Latest NAV</p>
            <Numeric className="font-mono text-2xl">
              {formatUsd(points[points.length - 1]!.nav, { compact: false, cents: false })}
            </Numeric>
          </div>
          <div className="text-right">
            <p className="text-[12px] uppercase tracking-[0.16em] text-fg-muted">
              Window P&amp;L
            </p>
            <Numeric tone={toneFor(headlinePnL)} className="font-mono text-lg">
              {formatPct(headlinePnLPct, { signed: true })}
            </Numeric>
          </div>
        </div>
        <Chart points={points} />
      </div>
    </section>
  );
}

function SectionHeader({
  window,
  onWindow,
}: {
  window: Window;
  onWindow: (_w: Window) => void;
}): JSX.Element {
  return (
    <header className="mb-2 flex items-baseline justify-between">
      <h2 className="text-[12px] uppercase tracking-[0.16em] text-fg-muted">NAV timeline</h2>
      <div className="flex gap-1">
        {(["24h", "7d", "30d"] as Window[]).map((w) => (
          <button
            key={w}
            type="button"
            onClick={() => onWindow(w)}
            className={cn(
              "rounded-sm border px-2 py-0.5 font-mono text-[12px] uppercase tracking-[0.12em]",
              window === w
                ? "border-amber/50 text-amber"
                : "border-surface-line text-fg-muted hover:border-amber/30 hover:text-fg-primary",
            )}
          >
            {w}
          </button>
        ))}
      </div>
    </header>
  );
}

type Point = { ts: number; nav: number; hwm: number };

function buildPoints(snapshots: NavSnapshotRow[], window: Window, chainId: number): Point[] {
  if (snapshots.length === 0) return [];
  const cutoff = Math.floor(Date.now() / 1000) - windowSeconds(window);

  // Subgraph emits desc; we want oldest → newest for the chart.
  const ordered = [...snapshots].sort((a, b) => Number(a.timestamp) - Number(b.timestamp));
  const filtered = ordered.filter((s) => Number(s.timestamp) >= cutoff);
  if (filtered.length < 2) return [];

  const out: Point[] = [];
  let runningHwm = 0;
  for (const s of filtered) {
    const nav = mUsdcRawToUsd(s.totalNAV, chainId);
    runningHwm = Math.max(runningHwm, nav);
    out.push({ ts: Number(s.timestamp), nav, hwm: runningHwm });
  }
  return out;
}

function windowSeconds(window: Window): number {
  if (window === "24h") return 24 * 3600;
  if (window === "7d") return 7 * 24 * 3600;
  return 30 * 24 * 3600;
}

function Chart({ points }: { points: Point[] }): JSX.Element {
  const width = 760;
  const height = 220;
  const padX = 28;
  const padTop = 8;
  const padBottom = 24;

  const xs = points.map((p) => p.ts);
  const navs = points.map((p) => p.nav);
  const hwms = points.map((p) => p.hwm);
  const yMin = Math.min(...navs) * 0.998;
  const yMax = Math.max(...hwms) * 1.002;

  const xScale = (x: number): number =>
    padX + ((x - xs[0]!) / Math.max(1, xs[xs.length - 1]! - xs[0]!)) * (width - padX * 2);
  const yScale = (y: number): number =>
    padTop + ((yMax - y) / Math.max(1e-9, yMax - yMin)) * (height - padTop - padBottom);

  const linePath = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${xScale(p.ts).toFixed(1)} ${yScale(p.nav).toFixed(1)}`)
    .join(" ");

  // Drawdown envelope: rectangle between HWM and NAV at each x.
  const envelopeTop = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${xScale(p.ts).toFixed(1)} ${yScale(p.hwm).toFixed(1)}`)
    .join(" ");
  const envelopeBottom = [...points]
    .reverse()
    .map((p) => `L ${xScale(p.ts).toFixed(1)} ${yScale(p.nav).toFixed(1)}`)
    .join(" ");
  const envelopePath = `${envelopeTop} ${envelopeBottom} Z`;

  // Y-axis grid lines — three steps, labels in mono so columns align.
  const ySteps = 3;
  const gridYs = Array.from({ length: ySteps + 1 }, (_, i) => yMin + ((yMax - yMin) * i) / ySteps);

  return (
    <svg
      role="img"
      aria-label="NAV timeline"
      viewBox={`0 0 ${width} ${height}`}
      className="block w-full"
      style={{ maxHeight: 260 }}
    >
      {/* grid */}
      {gridYs.map((y, i) => (
        <line
          key={i}
          x1={padX}
          x2={width - padX}
          y1={yScale(y)}
          y2={yScale(y)}
          stroke="var(--surface-line)"
          strokeWidth={0.5}
          strokeDasharray="2 4"
        />
      ))}
      {gridYs.map((y, i) => (
        <text
          key={`label-${i}`}
          x={padX - 4}
          y={yScale(y) + 3}
          textAnchor="end"
          className="fill-fg-muted font-mono"
          fontSize={9}
        >
          {formatUsd(y, { compact: true, cents: false })}
        </text>
      ))}

      {/* drawdown envelope */}
      <path d={envelopePath} fill="var(--signal-negative-dim)" opacity={0.35} />

      {/* NAV line */}
      <path d={linePath} fill="none" stroke="var(--accent-amber)" strokeWidth={1.5} />

      {/* axis ticks (start + end) */}
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
