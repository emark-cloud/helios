/**
 * /dashboard — DESIGN.md §9.3, "priority HIGHEST". Top strip,
 * allocator card, allocations table, live activity rail. Sunburst
 * deferred to Phase 4 per docs/phase1-plan.md WS4 scope.
 *
 * Server-rendered chrome + dynamic-imported client body so wagmi
 * hooks (`useAccount`) only run after the WagmiProvider mounts.
 */

import dynamic from "next/dynamic";

import { AppShell } from "@/components/chrome/AppShell";
import { PageHeader } from "@/components/chrome/PageHeader";

const DashboardClient = dynamic(
  () => import("@/components/dashboard/DashboardClient").then((m) => m.DashboardClient),
  {
    ssr: false,
    loading: () => (
      <div className="rounded-md border border-surface-line bg-surface-panel p-12 text-center text-sm text-fg-muted">
        Loading dashboard…
      </div>
    ),
  },
);

export default function DashboardPage(): JSX.Element {
  return (
    <AppShell>
      <PageHeader
        eyebrow="Phase 1 · live"
        title="Dashboard"
        summary="Your capital, the allocator's decisions, and a live event rail. Reads from the Helios subgraph and the Sentinel service."
      />
      <DashboardClient />
    </AppShell>
  );
}
