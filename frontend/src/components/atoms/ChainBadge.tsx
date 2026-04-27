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

export function ChainBadge({ chainId, className }: { chainId: number; className?: string }): JSX.Element {
  const name = chainName(chainId);
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-sm border px-1.5 py-0.5 text-[10px] uppercase tracking-[0.16em] font-mono",
        CHAIN_TOKEN[name],
        className,
      )}
    >
      {name}
    </span>
  );
}
