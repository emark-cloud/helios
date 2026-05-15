/**
 * Plainspoken summary above the sign button. DESIGN.md §6 voice — quiet
 * authority, no marketing copy. The user is about to sign a commitment;
 * the summary should make the meaningful constraints unmistakable.
 *
 * The delegation amount is the one figure the user most wants to see
 * (and adjust) right before they confirm, so it leads the card as an
 * inline-editable field rather than being buried in the template.
 */

"use client";

import { useEffect, useState, type ChangeEvent } from "react";

import { Numeric } from "@/components/atoms/Numeric";
import { formatBpsAsPct, formatStrategyClass } from "@/lib/format";
import type { TemplateForm } from "@/lib/templates";

export function CommitmentSummary({
  form,
  onAmountChange,
  disabled = false,
}: {
  form: TemplateForm;
  onAmountChange: (_usd: number) => void;
  disabled?: boolean;
}): JSX.Element {
  const classes = form.allowed_strategy_classes.map(formatStrategyClass).join(", ");
  const assets = form.allowed_assets.join(", ");
  const cadence = humanCadence(form.rebalance_cadence_sec);

  return (
    <div className="rounded-md border border-surface-line bg-surface-panel p-6">
      <h3 className="text-[12px] uppercase tracking-[0.16em] text-fg-muted">You are signing</h3>

      <AmountField
        valueUsd={form.max_capital_usd}
        onChange={onAmountChange}
        disabled={disabled}
      />

      <ul className="mt-4 flex flex-col gap-2 text-sm text-fg-secondary">
        <li>
          Allocator routes capital across {classes} strategies trading {assets}.
        </li>
        <li>
          No single strategy holds more than{" "}
          <Numeric>{formatBpsAsPct(form.max_per_strategy_bps)}</Numeric> of your capital.
        </li>
        <li>
          A strategy that breaches{" "}
          <Numeric tone="negative">−{formatBpsAsPct(form.drawdown_threshold_bps)}</Numeric>{" "}
          drawdown can be defunded by anyone — including you, including the chain itself.
        </li>
        <li>
          Strategies charging more than{" "}
          <Numeric>{formatBpsAsPct(form.max_fee_rate_bps)}</Numeric> in performance fees are
          excluded from your allocation.
        </li>
        <li>The allocator may rebalance as often as every {cadence}.</li>
        <li>You retain custody. Withdraw is one click on the dashboard, no permission needed.</li>
      </ul>
    </div>
  );
}

/**
 * Inline-editable delegation amount. `max_capital_usd` flows straight
 * into `formToContractStruct` (→ `maxCapital`) and the Passport
 * userOp's mint/approve/deposit legs, so what's typed here is what
 * gets minted and delegated.
 *
 * Local string state keeps the field editable mid-keystroke (so "15"
 * on the way to "1500" doesn't get floored out from under the user).
 * We only resync from the prop when it changes for an external reason
 * — picking a different template resets `max_capital_usd`.
 */
function AmountField({
  valueUsd,
  onChange,
  disabled,
}: {
  valueUsd: number;
  onChange: (_usd: number) => void;
  disabled: boolean;
}): JSX.Element {
  const [text, setText] = useState(String(valueUsd));

  useEffect(() => {
    const parsed = Math.floor(Number.parseFloat(text.replace(/,/g, "")));
    if (parsed !== valueUsd) setText(String(valueUsd));
    // Intentionally keyed on the external value only — including `text`
    // would resync on every keystroke and fight the in-progress edit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [valueUsd]);

  function handleChange(e: ChangeEvent<HTMLInputElement>): void {
    const raw = e.target.value;
    setText(raw);
    const n = Number.parseFloat(raw.replace(/,/g, ""));
    if (Number.isFinite(n) && n >= 1) onChange(Math.floor(n));
  }

  return (
    <div className="mt-4 rounded-sm border border-surface-line bg-surface-elev px-4 py-3">
      <label
        htmlFor="delegate-amount"
        className="text-[12px] uppercase tracking-[0.16em] text-fg-muted"
      >
        Amount you delegate
      </label>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="num text-lg text-fg-muted">$</span>
        <input
          id="delegate-amount"
          type="text"
          inputMode="numeric"
          value={text}
          onChange={handleChange}
          onBlur={() => setText(String(valueUsd))}
          disabled={disabled}
          aria-label="Amount you delegate, in mUSDC"
          className="num w-full min-w-0 bg-transparent text-lg text-fg-primary outline-none focus:text-amber-bright disabled:cursor-not-allowed disabled:opacity-50"
        />
        <span className="text-xs uppercase tracking-[0.16em] text-fg-muted">mUSDC</span>
      </div>
      <p className="mt-2 text-xs text-fg-secondary">
        The allocator may deploy up to this much across strategies. On testnet this is
        self-minted demo mUSDC — adjust it freely before you confirm.
      </p>
    </div>
  );
}

function humanCadence(seconds: number): string {
  if (seconds >= 3_600 && seconds % 3_600 === 0) {
    const h = seconds / 3_600;
    return h === 1 ? "1 hour" : `${h} hours`;
  }
  const m = Math.round(seconds / 60);
  return m === 1 ? "1 minute" : `${m} minutes`;
}
