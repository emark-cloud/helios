/**
 * Current allocator card — DESIGN.md §9.3 + §8.4.
 *
 * §8.4 calls out the two-sided market: users will see strategies AND
 * allocators. Naming the allocator on the dashboard is what makes the
 * tier visible. The card is intentionally one column on mobile, two on
 * desktop, with the fee + fee-tier as the dominant numeric.
 */

import { Numeric } from "@/components/atoms/Numeric";
import { formatBpsAsPct } from "@/lib/format";

export function AllocatorCard({
  name,
  feeRateBps,
}: {
  name: string;
  feeRateBps: number;
}): JSX.Element {
  return (
    <div className="rounded-md border border-surface-line bg-surface-panel p-5">
      <div className="flex items-baseline justify-between">
        <div>
          <div className="text-[12px] uppercase tracking-[0.16em] text-fg-muted">Allocator</div>
          <div className="mt-1.5 font-display text-base font-semibold text-fg-primary">{name}</div>
        </div>
        <span className="rounded-sm border border-amber/40 px-2 py-0.5 font-mono text-[12px] uppercase tracking-[0.16em] text-amber">
          Official Reference
        </span>
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
        <Row label="Performance fee">
          <Numeric>{formatBpsAsPct(feeRateBps)}</Numeric>
        </Row>
        <Row label="Custody">
          <span className="text-fg-secondary">User-retained</span>
        </Row>
      </dl>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }): JSX.Element {
  return (
    <div className="flex items-baseline justify-between">
      <dt className="text-fg-muted">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}
