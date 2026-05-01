/**
 * CohortDistribution — sparkline showing this strategy's normalized Sharpe
 * relative to its class cohort.
 *
 * `norm = (sharpe - cohort.median) / cohort.iqr` (Helios.md §8.2). On the
 * normalized axis the cohort median sits at 0 and the IQR spans ±0.5; we
 * draw that band and a marker at `norm`. Raw `sharpe` is shown alongside
 * so the reader can sanity-check the cohort transform.
 *
 * `is_fallback` (cohort below `min_cohort_size`) reduces the transform to
 * `sharpe / 1` against median=0 — we render the same shape but in a muted
 * tone so the viewer knows it's pre-cohort scaling.
 */

import { Numeric } from "@/components/atoms/Numeric";
import { cn } from "@/lib/cn";
import type { CohortStats } from "@/lib/reputation";

export type CohortDistributionProps = {
  windowLabel: string;
  rawSharpe: number;
  normalized: number;
  cohort: CohortStats;
};

const AXIS_MIN = -2;
const AXIS_MAX = 2;

export function CohortDistribution({
  windowLabel,
  rawSharpe,
  normalized,
  cohort,
}: CohortDistributionProps): JSX.Element {
  const fallback = cohort.is_fallback;
  const markerPct = pctForValue(clamp(normalized, AXIS_MIN, AXIS_MAX));
  const medianPct = pctForValue(0);
  const iqrLeftPct = pctForValue(-0.5);
  const iqrWidthPct = pctForValue(0.5) - iqrLeftPct;

  return (
    <div className="flex flex-col rounded-md border border-surface-line bg-surface-panel p-4">
      <div className="flex items-baseline justify-between">
        <span className="text-[11px] uppercase tracking-[0.16em] text-fg-muted">{windowLabel}</span>
        <span className="font-mono text-[11px] text-fg-muted">
          n={cohort.size}
          {fallback ? " · fallback" : ""}
        </span>
      </div>

      <div className="mt-3 flex items-baseline justify-between gap-3">
        <div>
          <p className="text-[10px] uppercase tracking-[0.16em] text-fg-muted">sharpe</p>
          <Numeric className="font-mono text-sm">{formatSigned(rawSharpe, 3)}</Numeric>
        </div>
        <div className="text-right">
          <p className="text-[10px] uppercase tracking-[0.16em] text-fg-muted">norm</p>
          <Numeric tone={normTone(normalized, fallback)} className="font-mono text-sm">
            {formatSigned(normalized, 3)}
          </Numeric>
        </div>
      </div>

      {/* Distribution axis */}
      <div className="relative mt-4 h-8 rounded-sm border border-surface-line bg-surface-elev">
        {/* IQR band */}
        <div
          className={cn(
            "absolute inset-y-1 rounded-sm",
            fallback ? "bg-fg-muted/15" : "bg-amber/15",
          )}
          style={{ left: `${iqrLeftPct}%`, width: `${iqrWidthPct}%` }}
          aria-hidden="true"
        />
        {/* Median tick */}
        <div
          className="absolute inset-y-0 w-px bg-surface-line-strong"
          style={{ left: `${medianPct}%` }}
          aria-hidden="true"
        />
        {/* Strategy marker */}
        <div
          className={cn(
            "absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border",
            fallback
              ? "border-fg-muted bg-fg-muted"
              : normalized >= 0
                ? "border-amber bg-amber"
                : "border-signal-negative bg-signal-negative",
          )}
          style={{ left: `${markerPct}%` }}
          aria-label={`Normalized Sharpe ${formatSigned(normalized, 3)}`}
        />
      </div>

      <div className="mt-2 flex justify-between font-mono text-[10px] text-fg-muted">
        <span>{AXIS_MIN.toFixed(1)}σ</span>
        <span>median</span>
        <span>+{AXIS_MAX.toFixed(1)}σ</span>
      </div>

      <div className="mt-3 flex items-center justify-between text-[11px] text-fg-muted">
        <span>
          median{" "}
          <span className="font-mono text-fg-secondary">{formatSigned(cohort.median, 3)}</span>
        </span>
        <span>
          IQR <span className="font-mono text-fg-secondary">{cohort.iqr.toFixed(3)}</span>
        </span>
      </div>
    </div>
  );
}

function pctForValue(v: number): number {
  return ((v - AXIS_MIN) / (AXIS_MAX - AXIS_MIN)) * 100;
}

function clamp(v: number, lo: number, hi: number): number {
  if (!Number.isFinite(v)) return 0;
  return Math.min(hi, Math.max(lo, v));
}

function formatSigned(v: number, digits: number): string {
  if (!Number.isFinite(v)) return "—";
  const body = v.toFixed(digits);
  if (v > 0) return `+${body}`;
  return body;
}

function normTone(value: number, fallback: boolean): "positive" | "negative" | "muted" | "default" {
  if (fallback) return "muted";
  if (!Number.isFinite(value) || value === 0) return "default";
  return value > 0 ? "positive" : "negative";
}
