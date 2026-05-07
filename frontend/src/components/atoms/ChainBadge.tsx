/**
 * Chain identifier chip. DESIGN.md §4.3 — chain colors are muted, used
 * only on these badges. Kite borrows the amber on purpose ("Kite is
 * home"); Base + Arbitrum get their own desaturated tones.
 */

import { chainName } from "@/lib/format";
import { cn } from "@/lib/cn";

const CHAIN_TOKEN: Record<string, string> = {
  Kite: "border-chain-kite/40 text-chain-kite",
  Base: "border-chain-base/40 text-chain-base",
  Arbitrum: "border-chain-arbitrum/40 text-chain-arbitrum",
  Anvil: "border-fg-muted/40 text-fg-muted",
  Unknown: "border-fg-muted/40 text-fg-muted",
};

export function ChainBadge({
  chainId,
  className,
  /** Single 600ms `helios-chain-pulse` keyframe — DESIGN.md §10.3
   *  cross-chain reputation arrival. The caller passes a key (e.g.
   *  the `firedAt` timestamp) so React remounts the element and the
   *  animation re-fires. Absence = badge stays static. */
  pulseKey,
  /** Tiny clock dot to the left, signalling a cross-chain rep update
   *  is in flight (LayerZero latency window). */
  inFlight,
}: {
  chainId: number;
  className?: string;
  pulseKey?: string | number;
  inFlight?: boolean;
}): JSX.Element {
  const name = chainName(chainId);
  return (
    <span className={cn("inline-flex items-center gap-1.5", className)}>
      {inFlight ? (
        <span
          aria-label="Cross-chain reputation update in flight"
          className="inline-block h-1.5 w-1.5 rounded-full bg-fg-muted"
          data-testid="chain-rep-inflight"
        />
      ) : null}
      <span
        key={pulseKey ?? "static"}
        className={cn(
          "inline-flex items-center rounded-sm border px-1.5 py-0.5 text-[12px] uppercase tracking-[0.16em] font-mono",
          CHAIN_TOKEN[name],
        )}
        style={
          pulseKey != null
            ? { animation: "helios-chain-pulse 600ms ease-out 1" }
            : undefined
        }
        data-testid={pulseKey != null ? "chain-pulse" : undefined}
      >
        {name}
      </span>
    </span>
  );
}
