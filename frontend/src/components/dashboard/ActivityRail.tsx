/**
 * Live activity rail. DESIGN.md §9.3 + §10.2 + §13.
 *
 * - Reads from `SentinelStreamProvider` so the WS subscription is
 *   shared with the AllocationsTable and DashboardCascade. One signed
 *   handshake powers all three surfaces.
 * - New entries enter at the top with an 80ms stagger; each entry
 *   itself appears instantly. No smooth easings.
 * - Defund events get the red left-border treatment.
 *
 * The rail is bounded to 50 entries (in the provider) to keep the
 * DOM cheap; older history lives on /audit (Phase 2).
 */

"use client";

import { Numeric } from "@/components/atoms/Numeric";
import { ProofBadge } from "@/components/atoms/ProofBadge";
import { useSentinelStream } from "@/components/motion/SentinelStream";
import { cn } from "@/lib/cn";
import { formatRelative, formatStrategyClass, formatUsd } from "@/lib/format";
import type { SentinelEvent, SentinelEventKind } from "@/lib/sentinel";

type ConnState = "connecting" | "open" | "closed" | "error";

export function ActivityRail(): JSX.Element {
  const { events, connState } = useSentinelStream();

  return (
    <aside className="flex h-full flex-col rounded-md border border-surface-line bg-surface-panel">
      <header className="flex items-baseline justify-between border-b border-surface-line px-4 py-2.5">
        <h3 className="text-[10px] uppercase tracking-[0.16em] text-fg-muted">Activity</h3>
        <ConnDot state={connState} />
      </header>
      <ol className="flex-1 overflow-y-auto">
        {events.length === 0 ? (
          <li className="px-4 py-6 text-center text-xs text-fg-muted">
            {connState === "open"
              ? "Waiting for events from Sentinel."
              : "Connecting to Sentinel…"}
          </li>
        ) : (
          events.map((evt, i) => <Entry key={evt.uid} evt={evt} index={i} />)
        )}
      </ol>
    </aside>
  );
}

function ConnDot({ state }: { state: ConnState }): JSX.Element {
  const tone =
    state === "open"
      ? "bg-signal-positive"
      : state === "error"
        ? "bg-signal-negative"
        : "bg-fg-muted";
  const label =
    state === "open"
      ? "Live"
      : state === "connecting"
        ? "Connecting"
        : state === "error"
          ? "Disconnected"
          : "Closed";
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider text-fg-muted">
      <span className={cn("h-1.5 w-1.5 rounded-full", tone)} aria-hidden />
      {label}
    </span>
  );
}

function Entry({ evt, index }: { evt: SentinelEvent; index: number }): JSX.Element {
  // 80ms stagger: each entry waits its index in line, then appears
  // instantly. CSS `animation-delay` is effectively a discrete timer
  // here — the keyframe is a 1ms opacity flip, not a fade. Reduced
  // motion zeroes the delay via the global token.
  const delayMs = Math.min(index * 80, 800);
  const isDefund =
    evt.kind === "STRATEGY_DEFUNDED" || evt.kind === "DEFUND_FINALIZED";
  return (
    <li
      data-defund-state={isDefund ? "breaching" : undefined}
      className="flex flex-col gap-1 border-b border-surface-line px-4 py-2.5 last:border-b-0"
      style={{ animation: "helios-rail-in 1ms linear forwards", animationDelay: `${delayMs}ms`, opacity: 0 }}
    >
      <div className="flex items-baseline justify-between gap-3">
        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-fg-secondary">
          {KIND_LABEL[evt.kind] ?? evt.kind}
        </span>
        <Numeric tone="muted" className="text-[10px]">
          {formatRelative(evt.timestamp)}
        </Numeric>
      </div>
      <p className="text-xs text-fg-primary">{describeEvent(evt)}</p>
      {evt.kind === "ALLOCATION_CREATED" || evt.kind === "ALLOCATION_INCREASED" ? (
        <ProofBadge state="valid" />
      ) : null}
    </li>
  );
}

const KIND_LABEL: Record<SentinelEventKind, string> = {
  META_STRATEGY_SET: "Signed",
  ALLOCATION_CREATED: "Allocation",
  ALLOCATION_INCREASED: "Topped up",
  ALLOCATION_DECREASED: "Trimmed",
  STRATEGY_DEFUNDED: "Defunded",
  REBALANCE_COMPLETE: "Rebalance",
  FEE_SETTLED: "Fee",
  DEFUND_TRIGGERED: "Defund triggered",
  DEFUND_ARMED: "Defund armed",
  DEFUND_FINALIZED: "Defund finalized",
  DEFUND_CANCELLED: "Defund cancelled",
  NAV_DIVERGENCE: "NAV divergence",
};

function describeEvent(evt: SentinelEvent): string {
  const where = evt.strategy ? formatStrategyClass(strategyClassFromReason(evt) ?? "") || "strategy" : "";
  const amount = evt.amount_usd > 0 ? formatUsd(evt.amount_usd, { cents: false }) : null;
  switch (evt.kind) {
    case "META_STRATEGY_SET":
      return "Meta-strategy signed. Allocator may begin routing capital.";
    case "ALLOCATION_CREATED":
      return amount ? `Allocator deployed ${amount} to ${where}.` : "New allocation opened.";
    case "ALLOCATION_INCREASED":
      return amount ? `Allocator increased ${where} by ${amount}.` : "Allocation increased.";
    case "ALLOCATION_DECREASED":
      return amount ? `Allocator trimmed ${where} by ${amount}.` : "Allocation trimmed.";
    case "STRATEGY_DEFUNDED":
      return evt.reason
        ? `${where || "Strategy"} defunded — ${evt.reason}.`
        : `${where || "Strategy"} defunded.`;
    case "REBALANCE_COMPLETE":
      return amount ? `Rebalance complete. Net change ${amount}.` : "Rebalance complete.";
    case "FEE_SETTLED":
      return amount ? `Performance fee settled — ${amount}.` : "Performance fee settled.";
    case "DEFUND_TRIGGERED": {
      // chain_watch packs observed drawdown bps into amount_usd and the
      // breach count into reason as "BREACH_<n>". Render both.
      const drawdownPct = (evt.amount_usd / 100).toFixed(2);
      const breach = evt.reason.match(/^BREACH_(\d+)/)?.[1];
      const bondNote = " Trigger bond locked, refunds on confirm.";
      return breach
        ? `${where || "Strategy"} defund triggered (observation ${breach}, ${drawdownPct}% drawdown).${bondNote}`
        : `${where || "Strategy"} defund triggered (${drawdownPct}% drawdown).${bondNote}`;
    }
    case "DEFUND_ARMED":
      return `${where || "Strategy"} defund armed — confirm window started, bond at risk if NAV recovers.`;
    case "DEFUND_FINALIZED":
      return evt.reason === "SLASHED_TO_USER"
        ? `${where || "Strategy"} defund finalized — NAV recovered, bond slashed to user.`
        : `${where || "Strategy"} defund finalized — capital recovered, bond refunded${amount ? `, ${amount} reward to triggerer` : ""}.`;
    case "DEFUND_CANCELLED":
      return evt.reason === "RECOVERED"
        ? `${where || "Strategy"} defund cancelled — NAV recovered, bond refunded.`
        : `${where || "Strategy"} defund cancelled — bond refunded.`;
    case "NAV_DIVERGENCE":
      return `${where || "Strategy"} NAV divergence flagged — under cash floor.`;
  }
}

/** Sentinel doesn't carry the class on the event payload yet; we extract from
 *  the freeform reason if it's there, otherwise fall back. */
function strategyClassFromReason(evt: SentinelEvent): string | null {
  const m = evt.reason.match(/(momentum_v1|mean_reversion_v1|yield_rotation_v1)/);
  return m ? m[1]! : null;
}
