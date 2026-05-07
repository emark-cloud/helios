/**
 * ComponentBreakdown — one card per §8.2 reputation component.
 *
 * Reads directly from the `/v1/audit/{actor}` payload. Performance is
 * the only signed component (range [-1, 1]); the rest are [0, 1]. The
 * card renders the raw value, the weight, and the contribution
 * (`weight × value`) so a viewer can read off how the aggregate score
 * was assembled without consulting the formula separately.
 *
 * `highlighted` flips the card to amber when this component is the
 * largest absolute contributor — DESIGN.md §4.3 reserves amber for
 * "the thing the page wants you to look at".
 */

import { Numeric } from "@/components/atoms/Numeric";
import { cn } from "@/lib/cn";

export type ComponentBreakdownProps = {
  label: string;
  weight: number;
  value: number;
  /** True when value can fall in [-1, 1]; false when only [0, 1]. */
  signed?: boolean;
  /** Subtitle / formula hint shown below the bar. */
  hint?: string;
  highlighted?: boolean;
};

export function ComponentBreakdown({
  label,
  weight,
  value,
  signed = false,
  hint,
  highlighted = false,
}: ComponentBreakdownProps): JSX.Element {
  const contribution = weight * value;

  return (
    <div
      className={cn(
        "flex flex-col rounded-md border bg-surface-panel p-4",
        highlighted ? "border-amber/60" : "border-surface-line",
      )}
    >
      <div className="flex items-baseline justify-between">
        <span className="text-[12px] uppercase tracking-[0.16em] text-fg-muted">{label}</span>
        <span className="font-mono text-[12px] text-fg-muted">w={weight.toFixed(2)}</span>
      </div>

      <div className="mt-3 flex items-baseline justify-between">
        <Numeric tone={highlighted ? "amber" : "default"} className="font-mono text-2xl">
          {formatValue(value, signed)}
        </Numeric>
        <div className="text-right">
          <p className="text-[12px] uppercase tracking-[0.16em] text-fg-muted">contribution</p>
          <Numeric tone={contributionTone(contribution)} className="font-mono text-sm">
            {formatContribution(contribution)}
          </Numeric>
        </div>
      </div>

      <ValueBar value={value} signed={signed} highlighted={highlighted} />

      {hint ? <p className="mt-3 text-[12px] leading-snug text-fg-muted">{hint}</p> : null}
    </div>
  );
}

function ValueBar({
  value,
  signed,
  highlighted,
}: {
  value: number;
  signed: boolean;
  highlighted: boolean;
}): JSX.Element {
  if (signed) {
    const clipped = clamp(value, -1, 1);
    const half = 50;
    const widthPct = Math.abs(clipped) * 50;
    const positive = clipped >= 0;
    return (
      <div className="mt-3 h-1.5 w-full overflow-hidden rounded-sm border border-surface-line bg-surface-elev">
        <div className="relative h-full w-full">
          <div className="absolute inset-y-0 left-1/2 w-px bg-surface-line-strong" />
          <div
            className={cn(
              "absolute inset-y-0",
              highlighted
                ? "bg-amber"
                : positive
                  ? "bg-signal-positive"
                  : "bg-signal-negative",
            )}
            style={{
              left: positive ? `${half}%` : `${half - widthPct}%`,
              width: `${widthPct}%`,
            }}
          />
        </div>
      </div>
    );
  }

  const clipped = clamp(value, 0, 1);
  return (
    <div className="mt-3 h-1.5 w-full overflow-hidden rounded-sm border border-surface-line bg-surface-elev">
      <div
        className={cn("h-full", highlighted ? "bg-amber" : "bg-fg-secondary")}
        style={{ width: `${clipped * 100}%` }}
      />
    </div>
  );
}

function formatValue(value: number, signed: boolean): string {
  if (!Number.isFinite(value)) return "—";
  const body = value.toFixed(3);
  if (!signed) return body;
  if (value > 0) return `+${body}`;
  return body;
}

function formatContribution(value: number): string {
  if (!Number.isFinite(value)) return "—";
  const body = value.toFixed(4);
  if (value > 0) return `+${body}`;
  return body;
}

function contributionTone(value: number): "positive" | "negative" | "muted" {
  if (!Number.isFinite(value) || value === 0) return "muted";
  return value > 0 ? "positive" : "negative";
}

function clamp(v: number, lo: number, hi: number): number {
  if (!Number.isFinite(v)) return lo;
  return Math.min(hi, Math.max(lo, v));
}
