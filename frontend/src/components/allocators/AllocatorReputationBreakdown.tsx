/**
 * Reputation breakdown panel for `/allocators/[name]`. Maps the
 * v1 weights from `docs/reputation-math.md §"Allocator reputation v1"`:
 *
 *   0.55 · aggregate user net P&L above HWM
 *   0.20 · drawdown discipline (defund-within-60s ratio)
 *   0.15 · user retention (30-day rolling churn-inverted)
 *   0.10 · stake size (log curve, parity with strategies)
 *
 * Phase 3 wires the engine + signer (WS5.A) but does not yet emit a
 * per-component breakdown into the subgraph — `AllocatorReputationUpdate`
 * carries the aggregate `delta`. Until WS5.B v2 emits components, this
 * panel renders the *weights themselves* alongside the latest aggregate
 * score so the UX matches the §8.2 explainer copy. When the subgraph
 * lifts components, callers swap in the live values.
 */

import { Numeric } from "@/components/atoms/Numeric";

const COMPONENTS: Array<{
  key: string;
  label: string;
  weight: number;
  blurb: string;
}> = [
  {
    key: "pnl",
    label: "User net P&L above HWM",
    weight: 0.55,
    blurb: "Aggregate realized P&L, net of fees, summed across all delegated users above each user's high-water mark.",
  },
  {
    key: "drawdown",
    label: "Drawdown discipline",
    weight: 0.2,
    blurb: "Fraction of breached drawdowns the allocator defunded within one tick (60s).",
  },
  {
    key: "retention",
    label: "User retention",
    weight: 0.15,
    blurb: "Inverted 30-day churn — users who keep capital with the allocator over the rolling window.",
  },
  {
    key: "stake",
    label: "Stake size",
    weight: 0.1,
    blurb: "Log curve over allocator stake, parity with §8.2 strategy StakeScore.",
  },
];

export type AllocatorReputationBreakdownProps = {
  currentReputation: string;
};

export function AllocatorReputationBreakdown({
  currentReputation,
}: AllocatorReputationBreakdownProps): JSX.Element {
  const reputation = readReputation(currentReputation);
  return (
    <section className="rounded-md border border-surface-line bg-surface-panel p-5">
      <header className="flex items-baseline justify-between">
        <h2 className="font-display text-sm font-semibold text-fg-primary">
          Reputation v1 breakdown
        </h2>
        <a
          href="https://github.com/emark-cloud/helios/blob/main/docs/reputation-math.md"
          target="_blank"
          rel="noreferrer"
          className="font-mono text-[12px] uppercase tracking-[0.16em] text-fg-secondary hover:text-amber"
        >
          docs/reputation-math.md →
        </a>
      </header>
      <p className="mt-1 text-xs text-fg-muted">
        Weights are the v1 first-cut. Per the §8.2 weight-change discipline
        any change is a v2 decision; this UI mirrors the docs verbatim.
      </p>

      <div className="mt-4 flex items-baseline gap-3 border-b border-surface-line pb-4">
        <Numeric tone={reputation > 50 ? "positive" : reputation > 0 ? "default" : "muted"}>
          {reputation.toFixed(1)}
        </Numeric>
        <span className="font-mono text-[12px] uppercase tracking-[0.16em] text-fg-muted">
          Aggregate score · most recent on-chain update
        </span>
      </div>

      <dl className="mt-4 grid grid-cols-1 gap-3">
        {COMPONENTS.map((c) => (
          <div key={c.key} className="grid grid-cols-[120px_1fr] items-baseline gap-3">
            <div className="flex items-baseline gap-2">
              <Numeric tone="amber">{(c.weight * 100).toFixed(0)}%</Numeric>
              <span className="font-mono text-[12px] uppercase tracking-[0.16em] text-fg-muted">
                {c.label}
              </span>
            </div>
            <p className="text-xs text-fg-secondary">{c.blurb}</p>
          </div>
        ))}
      </dl>
    </section>
  );
}

function readReputation(raw: string): number {
  const n = Number(raw);
  if (!Number.isFinite(n)) return 0;
  return Math.abs(n) > 1_000 ? n / 1e18 : n;
}
