/**
 * Sentinel REST + WebSocket client. Mirrors the API shape exposed by
 * `services/sentinel/src/sentinel/service.py` and the payload schemas in
 * `services/sentinel/src/sentinel/schemas.py`.
 *
 * Helios.md §13.3 — the dashboard pulls from this; the activity rail
 * subscribes via WS. When Sentinel is unreachable, callers render an
 * empty state rather than spinning forever.
 */

const BASE = (process.env.NEXT_PUBLIC_SENTINEL_URL ?? "http://localhost:8001").replace(/\/$/, "");
const HELIX_BASE = (process.env.NEXT_PUBLIC_HELIX_URL ?? "http://localhost:8006").replace(/\/$/, "");

/// Two reference allocator base URLs. The onboard `AllocatorPicker`
/// stores the user's pick in localStorage as `"sentinel" | "helix"`;
/// `postMetaStrategyTo` reads that and routes the POST.
///
/// Helix exposes the *same* REST surface as Sentinel (`POST
/// /v1/users/{user}/meta-strategy`, `GET /users/{user}/dashboard`,
/// etc.) — both services are built on top of `helios-allocator-sdk`'s
/// `AllocatorRuntime`, so the only thing that differs cross-service
/// is the base URL.
export type AllocatorChoice = "sentinel" | "helix";

export const ALLOCATOR_BASES: Record<AllocatorChoice, string> = {
  sentinel: BASE,
  helix: HELIX_BASE,
};

export type SentinelEventKind =
  | "META_STRATEGY_SET"
  | "ALLOCATION_CREATED"
  | "ALLOCATION_INCREASED"
  | "ALLOCATION_DECREASED"
  | "STRATEGY_DEFUNDED"
  | "REBALANCE_COMPLETE"
  | "FEE_SETTLED";

export type SentinelEvent = {
  user: string;
  kind: SentinelEventKind;
  strategy: string | null;
  amount_usd: number;
  reason: string;
  timestamp: number;
};

export type AllocationView = {
  strategy_id: string;
  chain_id: number;
  declared_class: string;
  capital_deployed_usd: number;
  high_water_mark_usd: number;
  current_nav_usd: number;
  drawdown_bps: number;
  defunded: boolean;
  last_rebalance_ts: number;
};

export type DashboardPayload = {
  user_address: string;
  total_capital_usd: number;
  total_nav_usd: number;
  realized_pnl_usd: number;
  fees_paid_usd: number;
  allocations: AllocationView[];
  allocator_name: string;
  allocator_fee_rate_bps: number;
};

export type StrategyDirectoryRow = {
  strategy_id: string;
  declared_class: string;
  chain_id: number;
  operator: string;
  fee_rate_bps: number;
  stake_amount_usd: number;
  max_capacity_usd: number;
  current_allocations_usd: number;
  reputation_score: number;
  realized_volatility_30d: number;
  sharpe_30d: number;
  max_drawdown_30d_bps: number;
};

export type MetaStrategyPayload = {
  user_address: string;
  allowed_strategy_classes: string[];
  allowed_assets: string[];
  allowed_chains: number[];
  max_capital_usd: number;
  max_per_strategy_bps: number;
  max_strategies_count: number;
  drawdown_threshold_bps: number;
  max_fee_rate_bps: number;
  rebalance_cadence_sec: number;
  valid_until: number;
  /**
   * Reputation cold-start (Helios.md §8.7 / WS7.B). `bootstrap_share_bps` of
   * total capital is reserved for strategies with `trades_attested <
   * min_attested_trades`, allocated stake-weighted with a flat performance
   * prior. Defaults: 1000 (10%) and 50 trades.
   */
  bootstrap_share_bps: number;
  min_attested_trades: number;
  /** [PASSPORT-STUB] EOA EIP-712 sig today; Passport sig once unblocked. */
  signature: string;
};

export class SentinelError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "SentinelError";
    this.status = status;
  }
}

async function request<T>(
  path: string,
  init?: RequestInit,
  signal?: AbortSignal,
  base: string = BASE,
): Promise<T> {
  const res = await fetch(`${base}/v1${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    signal,
  });
  if (!res.ok) throw new SentinelError(`Sentinel HTTP ${res.status}`, res.status);
  return (await res.json()) as T;
}

export function fetchDashboard(user: string, signal?: AbortSignal): Promise<DashboardPayload> {
  return request<DashboardPayload>(`/users/${user}/dashboard`, undefined, signal);
}

export function postMetaStrategy(payload: MetaStrategyPayload, signal?: AbortSignal): Promise<{ ok: boolean }> {
  return request(`/users/${payload.user_address}/meta-strategy`, {
    method: "POST",
    body: JSON.stringify(payload),
  }, signal);
}

/// Route the meta-strategy POST to a specific allocator's REST
/// surface. The allocator-picker step calls this with the user's
/// choice; `lib/onboard-storage.ts` persists the pick.
export function postMetaStrategyTo(
  choice: AllocatorChoice,
  payload: MetaStrategyPayload,
  signal?: AbortSignal,
): Promise<{ ok: boolean }> {
  return request(
    `/users/${payload.user_address}/meta-strategy`,
    { method: "POST", body: JSON.stringify(payload) },
    signal,
    ALLOCATOR_BASES[choice],
  );
}

export function fetchSentinelStrategies(
  filters: { cls?: string; chain_id?: number; min_reputation?: number } = {},
  signal?: AbortSignal,
): Promise<StrategyDirectoryRow[]> {
  const params = new URLSearchParams();
  if (filters.cls) params.set("cls", filters.cls);
  if (filters.chain_id != null) params.set("chain_id", String(filters.chain_id));
  if (filters.min_reputation != null) params.set("min_reputation", String(filters.min_reputation));
  const qs = params.toString();
  return request<StrategyDirectoryRow[]>(`/strategies${qs ? `?${qs}` : ""}`, undefined, signal);
}

/**
 * Subscribe to user-scoped Sentinel events. Returns a teardown.
 *
 * The WS path mirrors `WS /v1/users/{user}/events` in service.py.
 * Reconnects are caller-controlled — wire in TanStack Query / Zustand
 * with explicit reconnection state, not a silent loop.
 */
export function subscribeUserEvents(
  user: string,
  onEvent: (_e: SentinelEvent) => void,
  onStatus?: (_status: "open" | "closed" | "error") => void,
): () => void {
  const wsBase = BASE.replace(/^http/, "ws");
  const ws = new WebSocket(`${wsBase}/v1/users/${user}/events`);
  ws.onopen = () => onStatus?.("open");
  ws.onmessage = (evt) => {
    try {
      const data = JSON.parse(evt.data) as SentinelEvent;
      onEvent(data);
    } catch {
      // The Sentinel WS only ever emits well-formed JSON. A parse miss
      // means an upstream regression — surface it as an error status
      // rather than swallowing.
      onStatus?.("error");
    }
  };
  ws.onerror = () => {
    onStatus?.("error");
  };
  ws.onclose = () => {
    onStatus?.("closed");
  };
  return () => {
    if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
      ws.close();
    }
  };
}
