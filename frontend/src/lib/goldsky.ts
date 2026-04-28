/**
 * Goldsky GraphQL client. The subgraph schema lives at
 * `subgraph/schema.graphql`; queries here mirror the entities the
 * frontend needs.
 *
 * No third-party GraphQL client — the surface is small enough that
 * `fetch` + typed query builders is cheaper than dragging in
 * graphql-request or apollo. Cache via TanStack Query at the call site.
 */

const ENDPOINT = process.env.NEXT_PUBLIC_GOLDSKY_ENDPOINT ?? "";

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
): Promise<T> {
  if (!ENDPOINT) throw new GoldskyError("NEXT_PUBLIC_GOLDSKY_ENDPOINT not set", 0);
  const res = await fetch(ENDPOINT, {
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
  const data = await gqlRequest<{ strategies: StrategyDirectoryRow[] }>(
    STRATEGIES_QUERY,
    {
      first: opts.first ?? 100,
      orderBy: opts.orderBy ?? "currentReputation",
      orderDir: opts.orderDir ?? "desc",
    },
    signal,
  );
  return data.strategies;
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
  const data = await gqlRequest<{ trades: RecentTrade[] }>(
    RECENT_TRADES_QUERY,
    { first },
    signal,
  );
  return data.trades;
}
