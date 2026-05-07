/**
 * MiniSunburst — same component, clipped for `AllocatorCard` /
 * `/strategies/[id]` allocators panel placement. Per `DESIGN.md §11`
 * mini variant: 64×64, no center label, no tooltip.
 */

"use client";

import { useMemo } from "react";

import { chainName } from "@/lib/format";
import { cn } from "@/lib/cn";

import {
  computeSunburstLayout,
  type SunburstInput,
  type SunburstLayout,
  type SunburstSegment,
} from "./useSunburstLayout";

export type MiniSunburstProps = SunburstInput & {
  size?: number;
  selectedId?: string | null;
  className?: string;
  ariaLabel?: string;
};

export function MiniSunburst({
  strategies,
  allocator,
  size = 64,
  selectedId,
  className,
  ariaLabel,
}: MiniSunburstProps): JSX.Element {
  const layout = useMemo<SunburstLayout>(
    () => computeSunburstLayout({ strategies, allocator }, { size, mini: true }),
    [strategies, allocator, size],
  );

  return (
    <svg
      viewBox={`0 0 ${layout.size} ${layout.size}`}
      width={layout.size}
      height={layout.size}
      role="img"
      aria-label={ariaLabel ?? `${allocator.label}: ${strategies.length} strategies`}
      className={cn("block", className)}
    >
      {layout.segments.map((segment) => (
        <MiniSegment key={segment.id} segment={segment} selected={selectedId === segment.id} />
      ))}
      <circle
        cx={layout.cx}
        cy={layout.cy}
        r={layout.innerRadius - 1}
        fill="var(--surface-base)"
        stroke="var(--surface-line)"
        strokeWidth={0.75}
      />
    </svg>
  );
}

function MiniSegment({ segment, selected }: { segment: SunburstSegment; selected: boolean }): JSX.Element {
  const chain = chainName(segment.node.chainId);
  const fillVar = chain === "Kite"
    ? "var(--chain-kite)"
    : chain === "Base"
      ? "var(--chain-base)"
      : chain === "Arbitrum"
        ? "var(--chain-arbitrum)"
        : "var(--fg-muted)";
  const fill = selected ? "var(--accent-amber)" : fillVar;

  return (
    <path
      d={segment.d}
      fill={fill}
      stroke="var(--surface-base)"
      strokeWidth={0.5}
      opacity={selected ? 1 : 0.78}
    />
  );
}
