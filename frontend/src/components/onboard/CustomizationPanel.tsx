/**
 * Customization panel for /onboard. Five inputs, all editable on top
 * of the template defaults: asset universe (chips), max per-strategy
 * (bps slider), drawdown threshold (bps slider), max fee rate (bps
 * slider), rebalance cadence (preset chips).
 *
 * Sliders express bps directly (the chain-side unit) so what the user
 * sees is what gets signed.
 */

"use client";

import { useState, type ChangeEvent } from "react";

import { Numeric } from "@/components/atoms/Numeric";
import { cn } from "@/lib/cn";
import { formatBpsAsPct } from "@/lib/format";
import type { DefundForm, TemplateForm } from "@/lib/templates";

const ASSET_OPTIONS = ["KITE", "ETH", "BTC"];
const CADENCE_OPTIONS: Array<{ seconds: number; label: string }> = [
  { seconds: 900, label: "15m" },
  { seconds: 1_800, label: "30m" },
  { seconds: 3_600, label: "1h" },
  { seconds: 14_400, label: "4h" },
];

export type CustomizationPanelProps = {
  value: TemplateForm;
  onChange: (_next: TemplateForm) => void;
  defundValue: DefundForm;
  onDefundChange: (_next: DefundForm) => void;
};

export function CustomizationPanel({
  value,
  onChange,
  defundValue,
  onDefundChange,
}: CustomizationPanelProps): JSX.Element {
  const [advancedOpen, setAdvancedOpen] = useState(false);

  function patch<K extends keyof TemplateForm>(key: K, next: TemplateForm[K]): void {
    onChange({ ...value, [key]: next });
  }

  function toggleAsset(asset: string): void {
    const has = value.allowed_assets.includes(asset);
    const next = has
      ? value.allowed_assets.filter((a) => a !== asset)
      : [...value.allowed_assets, asset];
    if (next.length === 0) return; // never allow empty universe
    patch("allowed_assets", next);
  }

  return (
    <div className="grid grid-cols-1 gap-6 rounded-md border border-surface-line bg-surface-panel p-6 md:grid-cols-2">
      <Field label="Asset universe" hint="Strategies may only trade these assets.">
        <div className="flex flex-wrap gap-1.5">
          {ASSET_OPTIONS.map((asset) => {
            const active = value.allowed_assets.includes(asset);
            return (
              <button
                key={asset}
                type="button"
                onClick={() => toggleAsset(asset)}
                className={cn(
                  "rounded-sm border px-2 py-1 font-mono text-xs uppercase tracking-wider",
                  active
                    ? "border-amber/60 text-amber"
                    : "border-surface-line text-fg-secondary hover:border-surface-line-strong",
                )}
                aria-pressed={active}
              >
                {asset}
              </button>
            );
          })}
        </div>
      </Field>

      <Field label="Rebalance cadence" hint="How often the allocator can rotate capital.">
        <div className="flex flex-wrap gap-1.5">
          {CADENCE_OPTIONS.map((opt) => {
            const active = opt.seconds === value.rebalance_cadence_sec;
            return (
              <button
                key={opt.seconds}
                type="button"
                onClick={() => patch("rebalance_cadence_sec", opt.seconds)}
                className={cn(
                  "rounded-sm border px-2 py-1 font-mono text-xs uppercase tracking-wider",
                  active
                    ? "border-amber/60 text-amber"
                    : "border-surface-line text-fg-secondary hover:border-surface-line-strong",
                )}
                aria-pressed={active}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
      </Field>

      <BpsSlider
        label="Max per strategy"
        hint="Cap on the share of your capital any single strategy can hold."
        value={value.max_per_strategy_bps}
        onChange={(bps) => patch("max_per_strategy_bps", bps)}
        min={500}
        max={10_000}
        step={500}
      />

      <BpsSlider
        label="Drawdown threshold"
        hint="If a strategy breaches this drawdown, anyone can permissionlessly defund it."
        value={value.drawdown_threshold_bps}
        onChange={(bps) => patch("drawdown_threshold_bps", bps)}
        min={500}
        max={3_000}
        step={250}
        tone="negative"
      />

      <BpsSlider
        label="Max fee rate"
        hint="Strategies above this performance fee won't receive allocation."
        value={value.max_fee_rate_bps}
        onChange={(bps) => patch("max_fee_rate_bps", bps)}
        min={0}
        max={2_000}
        step={100}
      />

      <Field label="Max strategies" hint="Upper bound on the number of strategies receiving capital at once.">
        <div className="flex items-center gap-3">
          <input
            type="range"
            min={1}
            max={10}
            step={1}
            value={value.max_strategies_count}
            onChange={(e: ChangeEvent<HTMLInputElement>) =>
              patch("max_strategies_count", Number.parseInt(e.target.value, 10))
            }
            className="flex-1 accent-amber"
          />
          <Numeric>{value.max_strategies_count}</Numeric>
        </div>
      </Field>

      <div className="md:col-span-2">
        <button
          type="button"
          onClick={() => setAdvancedOpen((v) => !v)}
          aria-expanded={advancedOpen}
          className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.16em] text-fg-muted hover:text-fg-secondary"
        >
          <span aria-hidden>{advancedOpen ? "▾" : "▸"}</span>
          Advanced
        </button>
        {advancedOpen ? (
          <div className="mt-4 flex flex-col gap-6 border-t border-surface-line pt-6">
            <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
              <BpsSlider
                label="Cold-start share"
                hint="Reserve a slice of capital for new strategies that haven't yet attested enough trades to rank in the main pool."
                value={value.bootstrap_share_bps}
                onChange={(bps) => patch("bootstrap_share_bps", bps)}
                min={0}
                max={3_000}
                step={250}
              />
              <Field
                label="Graduation threshold"
                hint="Strategies above this many attested trades exit the cold-start pool and rank with the main filter."
              >
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min={0}
                    max={500}
                    step={10}
                    value={value.min_attested_trades}
                    onChange={(e: ChangeEvent<HTMLInputElement>) =>
                      patch("min_attested_trades", Number.parseInt(e.target.value, 10))
                    }
                    className="flex-1 accent-amber"
                  />
                  <Numeric>{value.min_attested_trades}</Numeric>
                </div>
              </Field>
            </div>
            <DefundControls value={defundValue} onChange={onDefundChange} />
          </div>
        ) : null}
      </div>
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <div className="flex flex-col gap-2">
      <div>
        <div className="text-[11px] uppercase tracking-[0.16em] text-fg-muted">{label}</div>
        {hint ? <div className="mt-1 text-xs text-fg-secondary">{hint}</div> : null}
      </div>
      {children}
    </div>
  );
}

/// WS7.C — Phase 4 editable defund controls (`docs/phase4-plan.md §4.10`).
/// Sliders feed `formToContractStruct`, which writes them into the on-chain
/// MetaStrategy struct. `MetaStrategyLib` substitutes its defaults on zero,
/// so the user can always pick "use defaults" by dragging to the minimum.
function DefundControls({
  value,
  onChange,
}: {
  value: DefundForm;
  onChange: (_next: DefundForm) => void;
}): JSX.Element {
  function patch<K extends keyof DefundForm>(key: K, next: DefundForm[K]): void {
    onChange({ ...value, [key]: next });
  }
  return (
    <div className="rounded-md border border-surface-line bg-surface-base/40 p-4">
      <div className="text-[11px] uppercase tracking-[0.16em] text-fg-muted">
        Auto-defund safety
      </div>
      <p className="mt-2 text-xs text-fg-secondary">
        Defunding a strategy requires the drawdown breach to hold across multiple
        observations spaced ≥ 5 minutes apart, and the caller to post a refundable USDC
        bond. Tighter bars + bigger bond = fewer false-positive defunds; looser =
        faster reaction.
      </p>
      <div className="mt-4 grid grid-cols-1 gap-5 sm:grid-cols-3">
        <DefundSlider
          label="TWAP bars"
          unit=""
          value={value.defund_twap_bars}
          onChange={(v) => patch("defund_twap_bars", v)}
          min={1}
          max={24}
          step={1}
          hint="Consecutive observations a breach must hold."
        />
        <DefundSlider
          label="Trigger bond"
          unit="bps"
          value={value.defund_bond_bps}
          onChange={(v) => patch("defund_bond_bps", v)}
          min={10}
          max={500}
          step={5}
          hint="Of the defunded position, refunded if the breach confirms."
        />
        <DefundSlider
          label="Confirm window"
          unit="blocks"
          value={value.defund_confirm_blocks}
          onChange={(v) => patch("defund_confirm_blocks", v)}
          min={1}
          max={60}
          step={1}
          hint="Bond slashed to user if NAV recovers in this window."
        />
      </div>
    </div>
  );
}

function DefundSlider({
  label,
  unit,
  value,
  onChange,
  min,
  max,
  step,
  hint,
}: {
  label: string;
  unit: string;
  value: number;
  onChange: (_v: number) => void;
  min: number;
  max: number;
  step: number;
  hint: string;
}): JSX.Element {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[10px] uppercase tracking-[0.14em] text-fg-muted">{label}</span>
        <Numeric>
          {value}
          {unit ? <span className="ml-0.5 text-fg-muted">{unit}</span> : null}
        </Numeric>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e: ChangeEvent<HTMLInputElement>) =>
          onChange(Number.parseInt(e.target.value, 10))
        }
        className="mt-1.5 w-full accent-amber"
        aria-label={label}
      />
      <p className="mt-1 text-[11px] text-fg-secondary">{hint}</p>
    </div>
  );
}

function BpsSlider({
  label,
  hint,
  value,
  onChange,
  min,
  max,
  step,
  tone,
}: {
  label: string;
  hint?: string;
  value: number;
  onChange: (_bps: number) => void;
  min: number;
  max: number;
  step: number;
  tone?: "negative";
}): JSX.Element {
  return (
    <Field label={label} hint={hint}>
      <div className="flex items-center gap-3">
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e: ChangeEvent<HTMLInputElement>) =>
            onChange(Number.parseInt(e.target.value, 10))
          }
          className="flex-1 accent-amber"
        />
        <Numeric tone={tone === "negative" ? "negative" : "default"}>
          {tone === "negative" ? "−" : ""}
          {formatBpsAsPct(value)}
        </Numeric>
      </div>
    </Field>
  );
}
