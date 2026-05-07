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
import type { TemplateForm } from "@/lib/templates";

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
};

export function CustomizationPanel({ value, onChange }: CustomizationPanelProps): JSX.Element {
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
            <DefundDefaults />
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

/// WS7.C — surface the auto-defund defaults the contract applies when the
/// caller passes zero. Read-only in Phase 2; Phase 4 wires the controls and
/// the bond UX on /dashboard.
function DefundDefaults(): JSX.Element {
  return (
    <div className="rounded-md border border-surface-line bg-surface-base/40 p-4">
      <div className="text-[11px] uppercase tracking-[0.16em] text-fg-muted">
        Auto-defund safety
      </div>
      <p className="mt-2 text-xs text-fg-secondary">
        Defunding requires the drawdown breach to persist across multiple oracle TWAP
        snapshots and the trigger caller to post a refundable bond. Defaults below — tuning
        ships in Phase 4.
      </p>
      <dl className="mt-3 grid grid-cols-1 gap-2 text-xs sm:grid-cols-3">
        <DefundRow label="TWAP bars" value="3" hint="5-min snapshots a breach must hold" />
        <DefundRow label="Trigger bond" value="0.50%" hint="bps of the position, refunded on confirm" />
        <DefundRow label="Confirm window" value="25 blocks" hint="bond slashed if NAV recovers" />
      </dl>
    </div>
  );
}

function DefundRow({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint: string;
}): JSX.Element {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-[0.14em] text-fg-muted">{label}</dt>
      <dd className="mt-0.5 font-mono text-fg-primary">{value}</dd>
      <div className="mt-0.5 text-[11px] text-fg-secondary">{hint}</div>
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
