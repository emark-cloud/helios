/**
 * Class + chain filter chips for /strategies. The amber active-state
 * is the only meaningful color use here per DESIGN.md §4.3.
 */

"use client";

import { cn } from "@/lib/cn";
import { chainName, formatStrategyClass } from "@/lib/format";

const CLASS_OPTIONS: Array<{ key: string | null; label: string }> = [
  { key: null, label: "All classes" },
  { key: "momentum_v1", label: formatStrategyClass("momentum_v1") },
  { key: "mean_reversion_v1", label: formatStrategyClass("mean_reversion_v1") },
  { key: "yield_rotation_v1", label: formatStrategyClass("yield_rotation_v1") },
];

const CHAIN_OPTIONS: Array<{ key: number | null; label: string }> = [
  { key: null, label: "All chains" },
  { key: 2368, label: chainName(2368) },
  { key: 84_532, label: chainName(84_532) },
  { key: 421_614, label: chainName(421_614) },
];

export type StrategiesFiltersProps = {
  classFilter: string | null;
  chainFilter: number | null;
  onClassFilter: (_cls: string | null) => void;
  onChainFilter: (_chain: number | null) => void;
};

export function StrategiesFilters({
  classFilter,
  chainFilter,
  onClassFilter,
  onChainFilter,
}: StrategiesFiltersProps): JSX.Element {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <FilterRow label="Class">
        {CLASS_OPTIONS.map((opt) => (
          <Chip
            key={String(opt.key)}
            active={classFilter === opt.key}
            onClick={() => onClassFilter(opt.key)}
          >
            {opt.label}
          </Chip>
        ))}
      </FilterRow>
      <FilterRow label="Chain">
        {CHAIN_OPTIONS.map((opt) => (
          <Chip
            key={String(opt.key)}
            active={chainFilter === opt.key}
            onClick={() => onChainFilter(opt.key)}
          >
            {opt.label}
          </Chip>
        ))}
      </FilterRow>
    </div>
  );
}

function FilterRow({ label, children }: { label: string; children: React.ReactNode }): JSX.Element {
  return (
    <div className="flex items-center gap-2">
      <span className="text-[12px] uppercase tracking-[0.16em] text-fg-muted">{label}</span>
      <div className="flex gap-1">{children}</div>
    </div>
  );
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-sm border px-2 py-1 font-mono text-[12px] uppercase tracking-wider",
        active
          ? "border-amber/60 text-amber"
          : "border-surface-line text-fg-secondary hover:border-surface-line-strong hover:text-fg-primary",
      )}
      aria-pressed={active}
    >
      {children}
    </button>
  );
}
