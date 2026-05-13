/**
 * Goldsky GraphQL client. The subgraph schema lives at
 * `subgraph/schema.graphql`; queries here mirror the entities the
 * frontend needs.
 *
 * No third-party GraphQL client — the surface is small enough that
 * `fetch` + typed query builders is cheaper than dragging in
 * graphql-request or apollo. Cache via TanStack Query at the call site.
 */

// Build-time injection. In production / dev the env var is set;
// in CI (Playwright e2e) it isn't, so fall back to a relative URL
// that contains "subgraphs" so test route mocks (`**/subgraphs/**`)
// can intercept. The page surface still surfaces the error state on
// the resulting 404 — see callers' `isError` branch.
const ENDPOINT =
  process.env.NEXT_PUBLIC_GOLDSKY_ENDPOINT && process.env.NEXT_PUBLIC_GOLDSKY_ENDPOINT.length > 0
    ? process.env.NEXT_PUBLIC_GOLDSKY_ENDPOINT
    : "/__test/subgraphs/unset";

// CXR-4 (2026-05-13) — optional per-chain subgraph endpoints for the
// §12.1 spot + yield venues. Each endpoint follows the same Goldsky
// schema as the canonical Kite endpoint; the frontend fans out reads
// in parallel and merges by entity id (`Strategy.id` is the registry
// address). When either is unset, the multi-chain helpers silently fall
// back to the canonical endpoint — Base/Arb subgraphs only become
// queryable once `pnpm --filter subgraph deploy:base|deploy:arbitrum`
// has actually run against Goldsky.
const ENDPOINT_BASE =
  process.env.NEXT_PUBLIC_GOLDSKY_ENDPOINT_BASE &&
  process.env.NEXT_PUBLIC_GOLDSKY_ENDPOINT_BASE.length > 0
    ? process.env.NEXT_PUBLIC_GOLDSKY_ENDPOINT_BASE
    : null;
const ENDPOINT_ARB =
  process.env.NEXT_PUBLIC_GOLDSKY_ENDPOINT_ARBITRUM &&
  process.env.NEXT_PUBLIC_GOLDSKY_ENDPOINT_ARBITRUM.length > 0
    ? process.env.NEXT_PUBLIC_GOLDSKY_ENDPOINT_ARBITRUM
    : null;

const CROSS_CHAIN_ENDPOINTS: Array<{ chainId: number; endpoint: string }> = [
  { chainId: 2368, endpoint: ENDPOINT },
  ...(ENDPOINT_BASE ? [{ chainId: 84532, endpoint: ENDPOINT_BASE }] : []),
  ...(ENDPOINT_ARB ? [{ chainId: 421614, endpoint: ENDPOINT_ARB }] : []),
];

export class GoldskyError extends Error {
  readonly status: number;
  readonly errors?: unknown;
  constructor(message: string, status: number, errors?: unknown) {
    super(message);
    this.name = "GoldskyError";
    this.status = status;
    this.errors = errors;
  }
}

export async function gqlRequest<T>(
  query: string,
  variables?: Record<string, unknown>,
  signal?: AbortSignal,
  endpoint: string = ENDPOINT,
): Promise<T> {
  const res = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, variables }),
    signal,
  });
  if (!res.ok) throw new GoldskyError(`Goldsky HTTP ${res.status}`, res.status);
  const body = (await res.json()) as { data?: T; errors?: unknown };
  if (body.errors) throw new GoldskyError("Goldsky returned errors", res.status, body.errors);
  if (!body.data) throw new GoldskyError("Goldsky returned empty body", res.status);
  return body.data;
}

// ── Strategies directory ────────────────────────────────────────────

export type StrategyDirectoryRow = {
  id: string;
  declaredClass: string;
  chainId: number;
  operator: string;
  feeRateBps: number;
  stakeAmount: string;
  maxCapacity: string;
  active: boolean;
  registeredAt: string;
  currentReputation: string;
  totalRealizedPnL: string;
  totalAttestedTrades: number;
  maxDrawdownBps: number;
};

const STRATEGIES_QUERY = /* GraphQL */ `
  query Strategies($first: Int!, $orderBy: Strategy_orderBy, $orderDir: OrderDirection) {
    strategies(first: $first, orderBy: $orderBy, orderDirection: $orderDir, where: { active: true }) {
      id
      declaredClass
      chainId
      operator
      feeRateBps
      stakeAmount
      maxCapacity
      active
      registeredAt
      currentReputation
      totalRealizedPnL
      totalAttestedTrades
      maxDrawdownBps
    }
  }
`;

export async function fetchStrategies(
  opts: { first?: number; orderBy?: string; orderDir?: "asc" | "desc" } = {},
  signal?: AbortSignal,
): Promise<StrategyDirectoryRow[]> {
  // CXR-4 — fan out across every configured chain subgraph in parallel.
  // The Goldsky schema is identical per chain; rows are deduped by
  // strategy id, with the row's `chainId` field stamped to the source
  // endpoint when the subgraph reports 0 (pre-CXR-4 indexes set chainId
  // to the active datasource via `getOrCreateStrategy`, but legacy
  // indexes — including the currently-deployed Kite v0.7.2 — may have
  // strategies that were bootstrapped from a Trade event before SR
  // registration fired, so `chainId=0` rows still appear).
  const variables = {
    first: opts.first ?? 100,
    orderBy: opts.orderBy ?? "currentReputation",
    orderDir: opts.orderDir ?? "desc",
  };
  const results = await Promise.allSettled(
    CROSS_CHAIN_ENDPOINTS.map(async ({ chainId, endpoint }) => {
      const data = await gqlRequest<{ strategies: StrategyDirectoryRow[] }>(
        STRATEGIES_QUERY,
        variables,
        signal,
        endpoint,
      );
      return data.strategies.map((s) => ({
        ...s,
        chainId: s.chainId > 0 ? s.chainId : chainId,
      }));
    }),
  );
  if (results.every((r) => r.status === "rejected")) {
    const first = results[0];
    if (first && first.status === "rejected") throw first.reason;
    throw new GoldskyError("Goldsky returned no data", 0);
  }
  const merged = new Map<string, StrategyDirectoryRow>();
  for (const r of results) {
    if (r.status !== "fulfilled") continue;
    for (const row of r.value) {
      if (!merged.has(row.id)) merged.set(row.id, row);
    }
  }
  return Array.from(merged.values());
}

// ── User dashboard ──────────────────────────────────────────────────

export type AllocationRow = {
  id: string;
  /** Per-event delta, NOT a running total. Sum across all of a user's
   *  allocation rows to get total capital deployed. See
   *  subgraph/schema.graphql comment on `Allocation.capitalDeployed`. */
  capitalDeployed: string;
  strategyHighWaterMark: string;
  lastRebalanceAt: string;
  defundedAt: string | null;
  defundReason: string | null;
  strategy: {
    id: string;
    declaredClass: string;
    chainId: number;
    currentReputation: string;
    feeRateBps: number;
    maxDrawdownBps: number;
  };
  allocator: {
    id: string;
    name: string;
  };
};

const USER_ALLOCATIONS_QUERY = /* GraphQL */ `
  query UserAllocations($user: Bytes!) {
    user(id: $user) {
      id
      allocations(orderBy: lastRebalanceAt, orderDirection: desc) {
        id
        capitalDeployed
        strategyHighWaterMark
        lastRebalanceAt
        defundedAt
        defundReason
        strategy {
          id
          declaredClass
          chainId
          currentReputation
          feeRateBps
          maxDrawdownBps
        }
        allocator {
          id
          name
        }
      }
    }
  }
`;

export async function fetchUserAllocations(
  user: string,
  signal?: AbortSignal,
): Promise<AllocationRow[]> {
  const data = await gqlRequest<{ user: { allocations: AllocationRow[] } | null }>(
    USER_ALLOCATIONS_QUERY,
    { user: user.toLowerCase() },
    signal,
  );
  return data.user?.allocations ?? [];
}

// ── Activity feed (used as a fallback when Sentinel WS is unreachable) ──

export type RecentTrade = {
  id: string;
  timestamp: string;
  txHash: string;
  proofValid: boolean;
  declaredClass: string;
  strategy: { id: string; chainId: number };
};

const RECENT_TRADES_QUERY = /* GraphQL */ `
  query RecentTrades($first: Int!) {
    trades(first: $first, orderBy: timestamp, orderDirection: desc) {
      id
      timestamp
      txHash
      proofValid
      declaredClass
      strategy {
        id
        chainId
      }
    }
  }
`;

export async function fetchRecentTrades(
  first: number = 25,
  signal?: AbortSignal,
): Promise<RecentTrade[]> {
  // CXR-4 — fan out across every configured chain subgraph in parallel
  // so /judge's recent-trades feed surfaces Base + Arb executions, not
  // just Kite. Order by timestamp after the merge so the chain mix in
  // the top N is genuine.
  const results = await Promise.allSettled(
    CROSS_CHAIN_ENDPOINTS.map(async ({ chainId, endpoint }) => {
      const data = await gqlRequest<{ trades: RecentTrade[] }>(
        RECENT_TRADES_QUERY,
        { first },
        signal,
        endpoint,
      );
      return data.trades.map((t) => ({
        ...t,
        strategy: {
          ...t.strategy,
          chainId: t.strategy.chainId > 0 ? t.strategy.chainId : chainId,
        },
      }));
    }),
  );
  const all: RecentTrade[] = [];
  for (const r of results) {
    if (r.status === "fulfilled") all.push(...r.value);
  }
  if (all.length === 0) {
    const first0 = results[0];
    if (first0 && first0.status === "rejected") throw first0.reason;
    return [];
  }
  all.sort((a, b) => Number(b.timestamp) - Number(a.timestamp));
  return all.slice(0, first);
}

// ── Allocators directory (`/allocators`) ────────────────────────────

export type AllocatorDirectoryRow = {
  id: string;
  name: string;
  operator: string;
  feeRateBps: number;
  stakeAmount: string;
  isReferenceBrand: boolean;
  active: boolean;
  registeredAt: string;
  totalUsers: number;
  totalCapitalManaged: string;
  currentReputation: string;
};

const ALLOCATORS_QUERY = /* GraphQL */ `
  query Allocators($first: Int!) {
    allocators(first: $first, orderBy: currentReputation, orderDirection: desc) {
      id
      name
      operator
      feeRateBps
      stakeAmount
      isReferenceBrand
      active
      registeredAt
      totalUsers
      totalCapitalManaged
      currentReputation
    }
  }
`;

export async function fetchAllocators(
  first: number = 50,
  signal?: AbortSignal,
): Promise<AllocatorDirectoryRow[]> {
  const data = await gqlRequest<{ allocators: AllocatorDirectoryRow[] }>(
    ALLOCATORS_QUERY,
    { first },
    signal,
  );
  return data.allocators;
}

// ── Allocator leaderboard (`/dashboard`) ────────────────────────────

export type AllocatorLeaderboardRow = AllocatorDirectoryRow & {
  reputationUpdates: { delta: string }[];
};

/// Top-N active allocators with the reputation deltas posted since
/// `$since` (unix seconds). Callers sum the deltas for the 24h figure
/// rather than burning a per-allocator round-trip.
const ALLOCATORS_LEADERBOARD_QUERY = /* GraphQL */ `
  query AllocatorsLeaderboard($first: Int!, $since: BigInt!) {
    allocators(
      first: $first
      where: { active: true }
      orderBy: currentReputation
      orderDirection: desc
    ) {
      id
      name
      operator
      feeRateBps
      stakeAmount
      isReferenceBrand
      active
      registeredAt
      totalUsers
      totalCapitalManaged
      currentReputation
      reputationUpdates(where: { timestamp_gte: $since }, first: 100) {
        delta
      }
    }
  }
`;

export async function fetchAllocatorLeaderboard(
  opts: { first?: number; since?: number } = {},
  signal?: AbortSignal,
): Promise<AllocatorLeaderboardRow[]> {
  const since = opts.since ?? Math.floor(Date.now() / 1000) - 24 * 3600;
  const data = await gqlRequest<{ allocators: AllocatorLeaderboardRow[] }>(
    ALLOCATORS_LEADERBOARD_QUERY,
    { first: opts.first ?? 5, since: since.toString() },
    signal,
  );
  return data.allocators;
}

// ── Allocator detail (`/allocators/[name]`) ──────────────────────────

export type AllocatorDecisionRow = {
  id: string;
  kind: string;
  amount: string;
  reason: string | null;
  timestamp: string;
  txHash: string;
  user: { id: string } | null;
  strategy: { id: string; declaredClass: string; chainId: number } | null;
};

export type UserDelegationRow = {
  id: string;
  capital: string;
  since: string;
  defundedAt: string | null;
  user: { id: string };
};

export type AllocatorReputationUpdateRow = {
  id: string;
  delta: string;
  newScore: string;
  timestamp: string;
  txHash: string;
};

export type AllocatorDetail = AllocatorDirectoryRow & {
  decisions: AllocatorDecisionRow[];
  delegations: UserDelegationRow[];
  reputationUpdates: AllocatorReputationUpdateRow[];
};

const ALLOCATOR_DETAIL_QUERY = /* GraphQL */ `
  query AllocatorDetail($id: Bytes!) {
    allocator(id: $id) {
      id
      name
      operator
      feeRateBps
      stakeAmount
      isReferenceBrand
      active
      registeredAt
      totalUsers
      totalCapitalManaged
      currentReputation
      decisions(first: 50, orderBy: timestamp, orderDirection: desc) {
        id
        kind
        amount
        reason
        timestamp
        txHash
        user { id }
        strategy { id declaredClass chainId }
      }
      delegations(first: 50, where: { defundedAt: null }, orderBy: since, orderDirection: desc) {
        id
        capital
        since
        defundedAt
        user { id }
      }
      reputationUpdates(first: 25, orderBy: timestamp, orderDirection: desc) {
        id
        delta
        newScore
        timestamp
        txHash
      }
    }
  }
`;

export async function fetchAllocatorDetail(
  id: string,
  signal?: AbortSignal,
): Promise<AllocatorDetail | null> {
  const data = await gqlRequest<{ allocator: AllocatorDetail | null }>(
    ALLOCATOR_DETAIL_QUERY,
    { id: id.toLowerCase() },
    signal,
  );
  return data.allocator;
}

/// `name` here is the URL-decoded allocator display name. Goldsky's
/// generated indexed-string filter is `where: { name: $name }`; we
/// pull the full row + nested fields in one query so the detail page
/// renders without a roundtrip.
const ALLOCATOR_BY_NAME_QUERY = /* GraphQL */ `
  query AllocatorByName($name: String!) {
    allocators(first: 1, where: { name: $name }) {
      id
      name
      operator
      feeRateBps
      stakeAmount
      isReferenceBrand
      active
      registeredAt
      totalUsers
      totalCapitalManaged
      currentReputation
      decisions(first: 50, orderBy: timestamp, orderDirection: desc) {
        id
        kind
        amount
        reason
        timestamp
        txHash
        user { id }
        strategy { id declaredClass chainId }
      }
      delegations(first: 50, where: { defundedAt: null }, orderBy: since, orderDirection: desc) {
        id
        capital
        since
        defundedAt
        user { id }
      }
      reputationUpdates(first: 25, orderBy: timestamp, orderDirection: desc) {
        id
        delta
        newScore
        timestamp
        txHash
      }
    }
  }
`;

export async function fetchAllocatorByName(
  name: string,
  signal?: AbortSignal,
): Promise<AllocatorDetail | null> {
  const data = await gqlRequest<{ allocators: AllocatorDetail[] }>(
    ALLOCATOR_BY_NAME_QUERY,
    { name },
    signal,
  );
  return data.allocators[0] ?? null;
}

// ── Strategy detail (`/strategies/[id]`) ────────────────────────────

export type StrategyTradeRow = {
  id: string;
  timestamp: string;
  txHash: string;
  proofValid: boolean;
  declaredClass: string;
  assetIn: string;
  assetOut: string;
  amountIn: string;
  minAmountOut: string;
  direction: number;
  blockWindowStart: string;
  blockWindowEnd: string;
};

export type StrategyAllocationRow = {
  id: string;
  capitalDeployed: string;
  strategyHighWaterMark: string;
  lastRebalanceAt: string;
  defundedAt: string | null;
  defundReason: string | null;
  user: { id: string };
  allocator: { id: string; name: string };
};

export type ParamsRotationRow = {
  id: string;
  oldHash: string;
  newHash: string;
  timestamp: string;
  txHash: string;
};

export type NavSnapshotRow = {
  id: string;
  totalNAV: string;
  timestamp: string;
};

export type StrategyDetail = StrategyDirectoryRow & {
  trades: StrategyTradeRow[];
  allocations: StrategyAllocationRow[];
  paramsRotations: ParamsRotationRow[];
  navSnapshots: NavSnapshotRow[];
};

const STRATEGY_DETAIL_QUERY = /* GraphQL */ `
  query StrategyDetail($id: Bytes!, $tradeFirst: Int!, $allocFirst: Int!, $navFirst: Int!) {
    strategy(id: $id) {
      id
      declaredClass
      chainId
      operator
      feeRateBps
      stakeAmount
      maxCapacity
      active
      registeredAt
      currentReputation
      totalRealizedPnL
      totalAttestedTrades
      maxDrawdownBps
      trades(first: $tradeFirst, orderBy: timestamp, orderDirection: desc) {
        id
        timestamp
        txHash
        proofValid
        declaredClass
        assetIn
        assetOut
        amountIn
        minAmountOut
        direction
        blockWindowStart
        blockWindowEnd
      }
      allocations(first: $allocFirst, orderBy: lastRebalanceAt, orderDirection: desc) {
        id
        capitalDeployed
        strategyHighWaterMark
        lastRebalanceAt
        defundedAt
        defundReason
        user { id }
        allocator { id name }
      }
      paramsRotations(first: 25, orderBy: timestamp, orderDirection: desc) {
        id
        oldHash
        newHash
        timestamp
        txHash
      }
      navSnapshots(first: $navFirst, orderBy: timestamp, orderDirection: desc) {
        id
        totalNAV
        timestamp
      }
    }
  }
`;

export async function fetchStrategyDetail(
  id: string,
  opts: { tradeFirst?: number; allocFirst?: number; navFirst?: number } = {},
  signal?: AbortSignal,
): Promise<StrategyDetail | null> {
  const data = await gqlRequest<{ strategy: StrategyDetail | null }>(
    STRATEGY_DETAIL_QUERY,
    {
      id: id.toLowerCase(),
      tradeFirst: opts.tradeFirst ?? 20,
      allocFirst: opts.allocFirst ?? 25,
      navFirst: opts.navFirst ?? 240,
    },
    signal,
  );
  return data.strategy;
}

// ── Strategy audit (`/audit/[strategy]`) — every trade ever, paginated ──

export type AuditTradeRow = StrategyTradeRow & {
  blockNumber: string;
};

export type StrategyAuditPage = {
  strategy: StrategyDirectoryRow & {
    trades: AuditTradeRow[];
    paramsRotations: ParamsRotationRow[];
  };
};

const STRATEGY_AUDIT_QUERY = /* GraphQL */ `
  query StrategyAudit($id: Bytes!, $first: Int!, $skip: Int!) {
    strategy(id: $id) {
      id
      declaredClass
      chainId
      operator
      feeRateBps
      stakeAmount
      maxCapacity
      active
      registeredAt
      currentReputation
      totalRealizedPnL
      totalAttestedTrades
      maxDrawdownBps
      trades(first: $first, skip: $skip, orderBy: timestamp, orderDirection: desc) {
        id
        timestamp
        txHash
        proofValid
        declaredClass
        assetIn
        assetOut
        amountIn
        minAmountOut
        direction
        blockWindowStart
        blockWindowEnd
      }
      paramsRotations(first: 50, orderBy: timestamp, orderDirection: desc) {
        id
        oldHash
        newHash
        timestamp
        txHash
      }
    }
  }
`;

export async function fetchStrategyAudit(
  id: string,
  opts: { first?: number; skip?: number } = {},
  signal?: AbortSignal,
): Promise<StrategyAuditPage["strategy"] | null> {
  const data = await gqlRequest<{ strategy: StrategyAuditPage["strategy"] | null }>(
    STRATEGY_AUDIT_QUERY,
    {
      id: id.toLowerCase(),
      first: opts.first ?? 50,
      skip: opts.skip ?? 0,
    },
    signal,
  );
  return data.strategy;
}

// ── Landing / judge stats ───────────────────────────────────────────

export type LandingStats = {
  /** Total capital under management — sum of every Allocation
   *  entity's capitalDeployed (per-event delta; subgraph note in
   *  schema.graphql). */
  totalCapitalUsdE6: string;
  activeStrategies: number;
  attestedTrades: number;
  activeAllocators: number;
  /** Recent on-chain `Trade` rows. Surfaced on /judge so a reviewer
   *  can click into Kitescan even when the VPS is offline (TODO.md
   *  line 371). */
  recentTrades: Array<{
    id: string;
    txHash: string;
    timestamp: string;
    strategy: { id: string; declaredClass: string; chainId: number };
    proofValid: boolean;
  }>;
};

const LANDING_STATS_QUERY = /* GraphQL */ `
  query LandingStats {
    strategies(first: 1000, where: { active: true }) {
      id
      totalAttestedTrades
    }
    allocators(first: 1000, where: { active: true }) {
      id
    }
    allocations(first: 1000) {
      capitalDeployed
    }
    trades(first: 12, orderBy: timestamp, orderDirection: desc) {
      id
      txHash
      timestamp
      proofValid
      strategy {
        id
        declaredClass
        chainId
      }
    }
  }
`;

export async function fetchLandingStats(signal?: AbortSignal): Promise<LandingStats> {
  type Raw = {
    strategies: Array<{ id: string; totalAttestedTrades: number }>;
    allocators: Array<{ id: string }>;
    allocations: Array<{ capitalDeployed: string }>;
    trades: LandingStats["recentTrades"];
  };
  const data = await gqlRequest<Raw>(LANDING_STATS_QUERY, undefined, signal);
  let totalE6 = 0n;
  for (const a of data.allocations) {
    try {
      totalE6 += BigInt(a.capitalDeployed);
    } catch {
      // Tolerate malformed rows so the page still renders.
    }
  }
  let attested = 0;
  for (const s of data.strategies) attested += s.totalAttestedTrades || 0;
  return {
    totalCapitalUsdE6: totalE6.toString(),
    activeStrategies: data.strategies.length,
    attestedTrades: attested,
    activeAllocators: data.allocators.length,
    recentTrades: data.trades,
  };
}
