/**
 * Strategy manifest header — name, class, operator, chain, registered
 * date, stake, fee rate, capacity used vs max. The first thing a
 * judge or auditor reads on `/strategies/[id]`.
 */

import { ChainBadge } from "@/components/atoms/ChainBadge";
import { Numeric } from "@/components/atoms/Numeric";
import {
  explorerAddressUrl,
  formatAddress,
  formatBpsAsPct,
  formatStrategyClass,
  formatTimestamp,
  formatUsd,
} from "@/lib/format";
import type { StrategyDetail } from "@/lib/goldsky";

export function ManifestHeader({ strategy }: { strategy: StrategyDetail }): JSX.Element {
  const stake = usdcToUsd(strategy.stakeAmount);
  const capacity = usdcToUsd(strategy.maxCapacity);

  const explorer = explorerAddressUrl(strategy.chainId, strategy.id);
  const operatorExplorer = explorerAddressUrl(strategy.chainId, strategy.operator);

  return (
    <section className="mb-6 rounded-md border border-surface-line bg-surface-panel p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="font-display text-xl text-fg-primary">
              {formatStrategyClass(strategy.declaredClass)}
            </h2>
            <ChainBadge chainId={strategy.chainId} />
            {strategy.active ? (
              <span className="rounded-sm border border-signal-positive-dim bg-signal-positive-dim/30 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.16em] text-signal-positive">
                Active
              </span>
            ) : (
              <span className="rounded-sm border border-surface-line bg-surface-elev px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.16em] text-fg-muted">
                Retired
              </span>
            )}
          </div>
          <p className="mt-1 font-mono text-xs text-fg-muted" title={strategy.id}>
            {explorer ? (
              <a href={explorer} target="_blank" rel="noreferrer" className="hover:text-amber">
                {formatAddress(strategy.id)}
              </a>
            ) : (
              formatAddress(strategy.id)
            )}
          </p>
        </div>

        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs sm:grid-cols-4">
          <Field label="Operator">
            {operatorExplorer ? (
              <a
                href={operatorExplorer}
                target="_blank"
                rel="noreferrer"
                className="font-mono text-fg-primary hover:text-amber"
                title={strategy.operator}
              >
                {formatAddress(strategy.operator)}
              </a>
            ) : (
              <span className="font-mono text-fg-primary" title={strategy.operator}>
                {formatAddress(strategy.operator)}
              </span>
            )}
          </Field>
          <Field label="Registered">
            <span className="font-mono text-fg-primary">
              {formatTimestamp(Number(strategy.registeredAt))}
            </span>
          </Field>
          <Field label="Stake">
            <Numeric>{formatUsd(stake, { compact: true, cents: false })}</Numeric>
          </Field>
          <Field label="Fee">
            <Numeric>{formatBpsAsPct(strategy.feeRateBps)}</Numeric>
          </Field>
          <Field label="Capacity">
            <Numeric>{formatUsd(capacity, { compact: true, cents: false })}</Numeric>
          </Field>
          <Field label="Trades attested">
            <Numeric>{strategy.totalAttestedTrades.toLocaleString()}</Numeric>
          </Field>
          <Field label="Max DD">
            <Numeric tone={strategy.maxDrawdownBps > 0 ? "negative" : "muted"}>
              {strategy.maxDrawdownBps > 0 ? `−${formatBpsAsPct(strategy.maxDrawdownBps)}` : "—"}
            </Numeric>
          </Field>
          <Field label="Reputation">
            <Numeric tone="amber">{readReputation(strategy.currentReputation).toFixed(1)}</Numeric>
          </Field>
        </dl>
      </div>
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }): JSX.Element {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-[0.16em] text-fg-muted">{label}</dt>
      <dd className="mt-0.5 font-mono">{children}</dd>
    </div>
  );
}

function usdcToUsd(raw: string): number {
  const n = Number(raw);
  if (!Number.isFinite(n)) return 0;
  return n / 1e6;
}

function readReputation(raw: string): number {
  const n = Number(raw);
  if (!Number.isFinite(n)) return 0;
  return Math.abs(n) > 1_000 ? n / 1e18 : n;
}
