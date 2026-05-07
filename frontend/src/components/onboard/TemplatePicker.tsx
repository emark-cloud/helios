/**
 * Template picker — three cards in a single row, amber border on the
 * selected one (DESIGN.md §10.2 active treatment). The picker drives
 * the form state defaults; users can override individual fields via
 * `<CustomizationPanel>` after picking.
 */

"use client";

import { Numeric } from "@/components/atoms/Numeric";
import { cn } from "@/lib/cn";
import { formatBpsAsPct } from "@/lib/format";
import { TEMPLATES, type TemplateKey } from "@/lib/templates";

export function TemplatePicker({
  value,
  onChange,
}: {
  value: TemplateKey;
  onChange: (_key: TemplateKey) => void;
}): JSX.Element {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
      {(Object.keys(TEMPLATES) as TemplateKey[]).map((key) => {
        const t = TEMPLATES[key];
        const active = key === value;
        return (
          <button
            type="button"
            key={key}
            onClick={() => onChange(key)}
            className={cn(
              "rounded-md border bg-surface-panel p-5 text-left transition-none",
              active
                ? "border-amber/60 ring-1 ring-amber/30"
                : "border-surface-line hover:border-surface-line-strong",
            )}
            aria-pressed={active}
          >
            <div className="flex items-baseline justify-between">
              <span className="font-display text-base font-semibold text-fg-primary">{t.label}</span>
              {active ? (
                <span className="font-mono text-[12px] uppercase tracking-[0.16em] text-amber">
                  Selected
                </span>
              ) : null}
            </div>
            <p className="mt-2 text-xs leading-relaxed text-fg-secondary">{t.blurb}</p>
            <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-[12px]">
              <Stat label="Max per strategy">
                <Numeric>{formatBpsAsPct(t.form.max_per_strategy_bps)}</Numeric>
              </Stat>
              <Stat label="Drawdown circuit">
                <Numeric tone="negative">−{formatBpsAsPct(t.form.drawdown_threshold_bps)}</Numeric>
              </Stat>
              <Stat label="Max fee rate">
                <Numeric>{formatBpsAsPct(t.form.max_fee_rate_bps)}</Numeric>
              </Stat>
              <Stat label="Rebalance">
                <Numeric>{cadenceLabel(t.form.rebalance_cadence_sec)}</Numeric>
              </Stat>
            </dl>
          </button>
        );
      })}
    </div>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }): JSX.Element {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <dt className="text-fg-muted">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function cadenceLabel(seconds: number): string {
  if (seconds % 3_600 === 0) return `${seconds / 3_600}h`;
  if (seconds % 60 === 0) return `${seconds / 60}m`;
  return `${seconds}s`;
}
