/**
 * /dashboard client body. Wired to the Sentinel REST + WS endpoints.
 * Connect-first: when no wallet is connected we render the call to
 * action rather than firing requests against a missing user.
 */

"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useAccount } from "wagmi";

import { ActivityRail } from "@/components/dashboard/ActivityRail";
import { AllocationsTable } from "@/components/dashboard/AllocationsTable";
import { AllocatorCard } from "@/components/dashboard/AllocatorCard";
import { AllocatorLeaderboard } from "@/components/dashboard/AllocatorLeaderboard";
import { DashboardTopStrip } from "@/components/dashboard/DashboardTopStrip";
import { WithdrawControl } from "@/components/dashboard/WithdrawControl";
import { fetchDashboard, type DashboardPayload } from "@/lib/sentinel";

export function DashboardClient(): JSX.Element {
  const { address, isConnected } = useAccount();

  const enabled = isConnected && Boolean(address);
  const query = useQuery<DashboardPayload, Error>({
    queryKey: ["dashboard", address],
    queryFn: ({ signal }) => fetchDashboard(address as string, signal),
    enabled,
    // Poll while healthy; freeze once Sentinel is unreachable so the
    // empty-state view doesn't flicker every 15s. Mirrors the
    // activity-rail's "one shot, refresh to retry" posture documented
    // in docs/local-testing.md.
    refetchInterval: (q) => (q.state.error ? false : 15_000),
    staleTime: 5_000,
    retry: false,
  });

  if (!enabled) {
    return (
      <div className="flex flex-col gap-6">
        <DisconnectedState />
        <AllocatorLeaderboard />
      </div>
    );
  }

  if (query.isLoading) {
    return <LoadingState />;
  }

  // 404 = the user has not signed a meta-strategy yet (per
  // services/sentinel/src/sentinel/service.py:147). Send them to
  // /onboard rather than treating it like an outage.
  const isNoMeta =
    query.isError && /404|no meta-strategy/i.test(query.error.message);
  if (isNoMeta) {
    return <NoMetaStrategyState />;
  }

  // Unreachable Sentinel: render the dashboard scaffold with empty
  // values so the layout is visible during local visual QA, and surface
  // the diagnostic as a top banner. DESIGN.md prefers stable
  // scaffolding to dialog-style errors.
  const data = query.isError ? EMPTY_PAYLOAD : query.data!;
  const unreachable = query.isError ? query.error.message : null;

  return (
    <div className="flex flex-col gap-6">
      {unreachable ? <UnreachableBanner message={unreachable} /> : null}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="flex flex-col gap-6">
          <DashboardTopStrip
            totalNavUsd={data.total_nav_usd}
            totalCapitalUsd={data.total_capital_usd}
            realizedPnlUsd={data.realized_pnl_usd}
            feesPaidUsd={data.fees_paid_usd}
          />
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(220px,300px)]">
            <AllocatorCard name={data.allocator_name} feeRateBps={data.allocator_fee_rate_bps} />
            <WithdrawControl totalNavUsd={data.total_nav_usd} />
          </div>
          <section>
            <h2 className="mb-2 text-[10px] uppercase tracking-[0.16em] text-fg-muted">
              Active allocations
            </h2>
            <AllocationsTable allocations={data.allocations} />
          </section>
          <AllocatorLeaderboard />
        </div>
        <div className="lg:sticky lg:top-16 lg:h-[calc(100vh-6rem)]">
          <ActivityRail user={address as string} />
        </div>
      </div>
    </div>
  );
}

const EMPTY_PAYLOAD: DashboardPayload = {
  user_address: "",
  total_capital_usd: 0,
  total_nav_usd: 0,
  realized_pnl_usd: 0,
  fees_paid_usd: 0,
  allocations: [],
  allocator_name: "—",
  allocator_fee_rate_bps: 0,
};

function DisconnectedState(): JSX.Element {
  return (
    <div className="rounded-md border border-surface-line bg-surface-panel p-12 text-center">
      <h2 className="font-display text-base font-semibold text-fg-primary">Connect a wallet</h2>
      <p className="mt-2 text-sm text-fg-secondary">
        The dashboard surfaces the meta-strategy you signed and the allocator&apos;s decisions on
        your capital. Connect the wallet you used to sign.
      </p>
      <Link
        href="/onboard"
        className="mt-4 inline-block rounded-sm border border-amber/40 px-3 py-1.5 font-mono text-xs uppercase tracking-[0.16em] text-amber hover:border-amber"
      >
        Or onboard now →
      </Link>
    </div>
  );
}

function LoadingState(): JSX.Element {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <div
          key={i}
          className="h-20 animate-pulse rounded-md border border-surface-line bg-surface-elev/30"
        />
      ))}
    </div>
  );
}

function NoMetaStrategyState(): JSX.Element {
  return (
    <div className="rounded-md border border-surface-line bg-surface-panel p-12 text-center">
      <h2 className="font-display text-base font-semibold text-fg-primary">No meta-strategy yet</h2>
      <p className="mt-2 text-sm text-fg-secondary">
        Sign a meta-strategy at <Link href="/onboard" className="text-amber hover:underline">/onboard</Link> and the allocator will start
        deploying capital. The cascade and the activity rail come alive from there.
      </p>
    </div>
  );
}

function UnreachableBanner({ message }: { message: string }): JSX.Element {
  return (
    <div className="rounded-md border border-signal-negative-dim bg-surface-panel px-4 py-3 text-xs">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-fg-primary">
          Sentinel unreachable —{" "}
          <span className="font-mono text-fg-muted">{message}</span>
        </p>
        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-fg-muted">
          Showing empty state
        </span>
      </div>
      <p className="mt-1 text-fg-secondary">
        Check that <code className="font-mono">NEXT_PUBLIC_SENTINEL_URL</code> points at a running
        Sentinel service. Default is <code>http://localhost:8001</code> for the docker-compose stack.
      </p>
    </div>
  );
}
