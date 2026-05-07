/**
 * Sunburst v1 — concentric two-ring viz per `DESIGN.md §11`.
 *
 *   inner ring → allocator (single segment)
 *   outer ring → strategies (one segment per allocation, sized by capital weight)
 *
 * Selected segment is amber (the only saturated color on the page).
 * Hover surfaces a tooltip; click navigates via `onSelect`.
 *
 * Motion budget per `DESIGN.md §13`: segments transition with a
 * `step-end`-flavored cubic (4 visible steps over `--tick-segment`).
 * `prefers-reduced-motion: reduce` collapses to instant via the
 * token in `tokens.css`.
 */

"use client";

import { useMemo, useState } from "react";

import { Numeric, toneFor } from "@/components/atoms/Numeric";
import { cn } from "@/lib/cn";
import { chainName, formatStrategyClass, formatUsd } from "@/lib/format";

import {
  computeSunburstLayout,
  type SunburstInput,
  type SunburstLayout,
  type SunburstSegment,
} from "./useSunburstLayout";

export type SunburstProps = SunburstInput & {
  size?: number;
  /** Highlights the matching segment in amber. */
  selectedId?: string | null;
  /** Click handler; receives the segment id and ring it belongs to. */
  onSelect?: (_id: string, _ring: "allocator" | "strategy") => void;
  /** Render labels in the center of the chart. v1: name + capital. */
  centerLabel?: { primary: string; secondary?: string };
  className?: string;
  /** Optional `aria-label` override; defaults to a strategy summary. */
  ariaLabel?: string;
};

export function Sunburst({
  strategies,
  allocator,
  size = 320,
  selectedId,
  onSelect,
  centerLabel,
  className,
  ariaLabel,
}: SunburstProps): JSX.Element {
  const layout = useMemo<SunburstLayout>(
    () => computeSunburstLayout({ strategies, allocator }, { size }),
    [strategies, allocator, size],
  );
  const [hoverId, setHoverId] = useState<string | null>(null);

  const total = strategies.reduce((acc, s) => acc + (s.capitalUsd ?? 0), 0);
  const label =
    ariaLabel ??
    `Allocator ${allocator.label} routing capital to ${strategies.length} strategies${
      total > 0 ? ` (${formatUsd(total, { compact: true, cents: false })})` : ""
    }`;

  const hovered = hoverId ? layout.segments.find((s) => s.id === hoverId) ?? null : null;

  return (
    <div className={cn("relative inline-flex flex-col", className)}>
      <svg
        viewBox={`0 0 ${layout.size} ${layout.size}`}
        width={layout.size}
        height={layout.size}
        role="img"
        aria-label={label}
        className="block"
        onMouseLeave={() => setHoverId(null)}
      >
        {/* Background guide ring — sits between rings as a soft seam. */}
        <circle
          cx={layout.cx}
          cy={layout.cy}
          r={layout.guideRadius}
          fill="none"
          stroke="var(--surface-line)"
          strokeWidth={1}
          strokeDasharray="2 3"
          opacity={0.4}
        />

        {/* Segments. Allocator first so strategy ring layers on top
            of any pixel where they touch (defensive). */}
        {layout.segments.map((segment) => (
          <SegmentPath
            key={segment.id}
            segment={segment}
            selected={selectedId === segment.id}
            hovered={hoverId === segment.id}
            onMouseEnter={() => setHoverId(segment.id)}
            onClick={() => onSelect?.(segment.id, segment.ring)}
          />
        ))}

        {/* Inner cap — keeps a clean center for `centerLabel`. */}
        <circle
          cx={layout.cx}
          cy={layout.cy}
          r={layout.innerRadius - 1}
          fill="var(--surface-base)"
          stroke="var(--surface-line)"
          strokeWidth={1}
        />

        {centerLabel ? (
          <g aria-hidden>
            <text
              x={layout.cx}
              y={layout.cy - 2}
              textAnchor="middle"
              className="fill-fg-primary font-mono"
              fontSize={size > 200 ? 14 : 10}
            >
              {centerLabel.primary}
            </text>
            {centerLabel.secondary ? (
              <text
                x={layout.cx}
                y={layout.cy + 12}
                textAnchor="middle"
                className="fill-fg-muted font-mono"
                fontSize={size > 200 ? 10 : 8}
              >
                {centerLabel.secondary}
              </text>
            ) : null}
          </g>
        ) : null}
      </svg>

      {hovered ? <SegmentTooltip segment={hovered} containerSize={layout.size} /> : null}
    </div>
  );
}

type SegmentPathProps = {
  segment: SunburstSegment;
  selected: boolean;
  hovered: boolean;
  onMouseEnter: () => void;
  onClick: () => void;
};

function SegmentPath({ segment, selected, hovered, onMouseEnter, onClick }: SegmentPathProps): JSX.Element {
  // Chain color is the segment fill. Amber overrides for the selected
  // segment — DESIGN §4.3 reserves amber for the focus thread.
  const chain = chainName(segment.node.chainId);
  const fillVar = chain === "Kite"
    ? "var(--chain-kite)"
    : chain === "Base"
      ? "var(--chain-base)"
      : chain === "Arbitrum"
        ? "var(--chain-arbitrum)"
        : "var(--fg-muted)";

  const fill = selected ? "var(--accent-amber)" : fillVar;
  // Hover: lift opacity, not color. Keeps green/red and chain colors
  // honest (DESIGN §4.3 — chain colors are muted, not interactive).
  const opacity = selected ? 1 : hovered ? 0.95 : 0.72;

  return (
    <path
      d={segment.d}
      fill={fill}
      stroke="var(--surface-base)"
      strokeWidth={1}
      opacity={opacity}
      style={{
        // Step-end-ish curve over --tick-segment for the discrete
        // "rebalance ticked" feel. Reduced-motion zeroes the var.
        transition: "opacity var(--tick-cascade), fill var(--tick-segment) steps(4, end)",
        cursor: "pointer",
      }}
      onMouseEnter={onMouseEnter}
      onClick={onClick}
      role="button"
      tabIndex={0}
      aria-label={`${segment.ring === "allocator" ? "Allocator" : "Strategy"}: ${segment.label}`}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
    />
  );
}

function SegmentTooltip({
  segment,
  containerSize,
}: {
  segment: SunburstSegment;
  containerSize: number;
}): JSX.Element {
  const { node, ring } = segment;
  const pnl =
    node.navUsd != null && node.capitalUsd != null && node.capitalUsd > 0
      ? node.navUsd - node.capitalUsd
      : null;
  // Anchor below the chart so the tooltip never clips against the
  // page edge for the dashboard placement.
  return (
    <div
      role="tooltip"
      style={{ width: containerSize }}
      className="pointer-events-none mt-3 select-none rounded-md border border-surface-line bg-surface-panel px-3 py-2 text-xs"
    >
      <div className="flex items-baseline justify-between gap-3">
        <span className="font-mono text-fg-primary">{segment.label}</span>
        <span className="text-[12px] uppercase tracking-[0.16em] text-fg-muted">{ring}</span>
      </div>
      <div className="mt-1 flex items-baseline justify-between gap-3 text-fg-secondary">
        <span>
          {node.declaredClass ? formatStrategyClass(node.declaredClass) : chainName(node.chainId)}
        </span>
        {node.capitalUsd != null ? (
          <Numeric tone="muted" align="right">
            {formatUsd(node.capitalUsd, { compact: true, cents: false })}
          </Numeric>
        ) : null}
      </div>
      {pnl != null ? (
        <div className="mt-1 flex items-baseline justify-between gap-3 text-[12px] text-fg-muted">
          <span>P&amp;L</span>
          <Numeric tone={toneFor(pnl)} align="right">
            {pnl >= 0 ? "+" : ""}
            {formatUsd(pnl, { compact: true, cents: false })}
          </Numeric>
        </div>
      ) : null}
    </div>
  );
}
