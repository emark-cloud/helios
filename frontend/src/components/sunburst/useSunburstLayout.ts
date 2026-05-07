/**
 * Sunburst layout — pure geometry. Maps the user → allocator →
 * strategies tree from `DESIGN.md §11` to SVG arc paths so the
 * `Sunburst` component is rendering, not computing.
 *
 * v1 scope: two rings (allocator + strategies). The positions ring
 * (per `DESIGN.md §11`) is roadmap; segments are sized linearly by
 * `weight` (capital weight, summing to ≤1 within a ring).
 *
 * No d3 dependency — the arc path is a few lines of trig and keeps
 * the frontend bundle lean.
 */

export type SunburstNode = {
  /** Stable identifier; click-through routes use this. */
  id: string;
  /** Display name (tooltip, mini-sunburst pluralised aria-label). */
  label: string;
  /** Capital weight in [0, 1]. Segments are normalized so the ring
   *  spans the full circle even if `Σ weight < 1`. */
  weight: number;
  /** Chain id — segment fill color comes from `--chain-{name}`. */
  chainId: number;
  /** Optional class slug or other secondary metadata for tooltips. */
  declaredClass?: string;
  /** Optional capital amount in USD for tooltip display. */
  capitalUsd?: number;
  /** Optional NAV for tooltip P&L computation. */
  navUsd?: number;
};

export type SunburstInput = {
  /** Outer ring — strategies the allocator routes capital into. */
  strategies: SunburstNode[];
  /** Inner ring — single allocator (v1 supports one allocator). */
  allocator: SunburstNode;
};

export type SunburstSegment = {
  id: string;
  label: string;
  /** Pre-computed `<path d="...">` payload. */
  d: string;
  /** Mid-arc cartesian coords (for label/anchor placement). */
  midX: number;
  midY: number;
  /** Source node so callers can read chain/class/capital for tooltips. */
  node: SunburstNode;
  /** Which ring this segment belongs to. */
  ring: "allocator" | "strategy";
  /** Start/end angles in radians (-π/2 = top of circle, clockwise). */
  startAngle: number;
  endAngle: number;
};

export type SunburstLayout = {
  /** SVG viewBox-friendly dimensions. */
  size: number;
  /** Radius of the inner cap (no rendered ring inside this). */
  innerRadius: number;
  /** Outer radius of the allocator (inner) ring. */
  allocatorOuterRadius: number;
  /** Outer radius of the strategies (outer) ring. */
  strategiesOuterRadius: number;
  /** Background guide circle radius (sits between rings). */
  guideRadius: number;
  /** Per-segment arc paths, ready to render. */
  segments: SunburstSegment[];
  /** Center of canvas. */
  cx: number;
  cy: number;
};

const TWO_PI = Math.PI * 2;
// Top of circle is the canonical 12-o'clock origin so the dominant
// (or focused) segment lands on top in mini-sunbursts.
const ROT0 = -Math.PI / 2;
// Tiny gap between segments so they read as distinct slices, not a
// single pie. 0.005 rad ≈ 0.3° — narrow enough to keep the ring
// readable at 64px.
const SEGMENT_GAP_RAD = 0.005;

export type LayoutOptions = {
  size?: number;
  /** True when sized for `MiniSunburst` — collapses padding. */
  mini?: boolean;
};

/** Pure: same input → same paths. The component memoizes on
 *  `(strategies, allocator, size)` so React re-renders don't recompute. */
export function computeSunburstLayout(
  input: SunburstInput,
  opts: LayoutOptions = {},
): SunburstLayout {
  const size = opts.size ?? (opts.mini ? 64 : 320);
  const cx = size / 2;
  const cy = size / 2;

  // Ring radii — v1 fixes the proportions; tuned so the allocator
  // ring is dominant but the outer (strategies) ring still has room
  // for ≤8 segments to read individually.
  const outer = size / 2 - (opts.mini ? 1 : 6);
  const innerCap = opts.mini ? size * 0.18 : size * 0.18;
  const allocatorOuterRadius = innerCap + (outer - innerCap) * 0.42;
  const strategiesOuterRadius = outer;
  const guideRadius = allocatorOuterRadius + (strategiesOuterRadius - allocatorOuterRadius) * 0.5;

  const segments: SunburstSegment[] = [];

  // Allocator ring is a single segment (v1 supports one allocator).
  segments.push(
    arcSegment({
      id: input.allocator.id,
      node: input.allocator,
      label: input.allocator.label,
      ring: "allocator",
      startAngle: ROT0,
      endAngle: ROT0 + TWO_PI - SEGMENT_GAP_RAD,
      innerRadius: innerCap,
      outerRadius: allocatorOuterRadius,
      cx,
      cy,
    }),
  );

  // Outer ring: strategies, weights normalized to a full circle.
  const totalWeight = input.strategies.reduce((acc, s) => acc + Math.max(0, s.weight), 0);
  if (totalWeight > 0 && input.strategies.length > 0) {
    const usableArc = TWO_PI - SEGMENT_GAP_RAD * input.strategies.length;
    let angle = ROT0;
    for (const strat of input.strategies) {
      const sweep = (Math.max(0, strat.weight) / totalWeight) * usableArc;
      segments.push(
        arcSegment({
          id: strat.id,
          node: strat,
          label: strat.label,
          ring: "strategy",
          startAngle: angle,
          endAngle: angle + sweep,
          innerRadius: allocatorOuterRadius + (opts.mini ? 1 : 4),
          outerRadius: strategiesOuterRadius,
          cx,
          cy,
        }),
      );
      angle += sweep + SEGMENT_GAP_RAD;
    }
  }

  return {
    size,
    cx,
    cy,
    innerRadius: innerCap,
    allocatorOuterRadius,
    strategiesOuterRadius,
    guideRadius,
    segments,
  };
}

type ArcInput = {
  id: string;
  node: SunburstNode;
  label: string;
  ring: "allocator" | "strategy";
  startAngle: number;
  endAngle: number;
  innerRadius: number;
  outerRadius: number;
  cx: number;
  cy: number;
};

function arcSegment(a: ArcInput): SunburstSegment {
  const d = arcPath(a.cx, a.cy, a.innerRadius, a.outerRadius, a.startAngle, a.endAngle);
  const midAngle = (a.startAngle + a.endAngle) / 2;
  const midR = (a.innerRadius + a.outerRadius) / 2;
  return {
    id: a.id,
    label: a.label,
    node: a.node,
    ring: a.ring,
    d,
    midX: a.cx + midR * Math.cos(midAngle),
    midY: a.cy + midR * Math.sin(midAngle),
    startAngle: a.startAngle,
    endAngle: a.endAngle,
  };
}

/** SVG ring-segment path. Two arcs (outer cw, inner ccw) joined by
 *  radial line segments. `largeArcFlag` set when the segment exceeds
 *  half the circle — required for the allocator-only ring. */
export function arcPath(
  cx: number,
  cy: number,
  innerR: number,
  outerR: number,
  start: number,
  end: number,
): string {
  const sweep = end - start;
  const large = sweep > Math.PI ? 1 : 0;

  const x0o = cx + outerR * Math.cos(start);
  const y0o = cy + outerR * Math.sin(start);
  const x1o = cx + outerR * Math.cos(end);
  const y1o = cy + outerR * Math.sin(end);
  const x1i = cx + innerR * Math.cos(end);
  const y1i = cy + innerR * Math.sin(end);
  const x0i = cx + innerR * Math.cos(start);
  const y0i = cy + innerR * Math.sin(start);

  return [
    `M ${x0o.toFixed(3)} ${y0o.toFixed(3)}`,
    `A ${outerR.toFixed(3)} ${outerR.toFixed(3)} 0 ${large} 1 ${x1o.toFixed(3)} ${y1o.toFixed(3)}`,
    `L ${x1i.toFixed(3)} ${y1i.toFixed(3)}`,
    `A ${innerR.toFixed(3)} ${innerR.toFixed(3)} 0 ${large} 0 ${x0i.toFixed(3)} ${y0i.toFixed(3)}`,
    "Z",
  ].join(" ");
}
