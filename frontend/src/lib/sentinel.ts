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
   * Replay-protection nonce. A fresh 64-bit value minted per signing
   * attempt by the frontend; the server records (user, nonce) and
   * rejects duplicates within the `valid_until` window. Without this
   * a captured signature could be re-submitted indefinitely up to
   * `valid_until`. JS numbers safely represent up to 2^53 — we mint
   * within that range to keep JSON round-tripping exact across both
   * the digest path and the wire payload.
   */
  nonce: number;
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
 * Reproduce `helios_allocator.service.auth.ws_subscribe_digest` in the
 * browser. The address is lower-cased; the JSON body has sorted keys
 * and no whitespace, byte-identical to the Python serializer so
 * `personal_sign` over either side recovers to the same address.
 */
export function wsSubscribeDigest(user: string, validUntil: number): string {
  const body = JSON.stringify({ user: user.toLowerCase(), valid_until: validUntil });
  return `Helios ws subscribe v1\n${body}`;
}

/**
 * Subscribe to user-scoped Sentinel events. Returns a teardown.
 *
 * The WS path mirrors `WS /v1/users/{user}/events` in service.py.
 * `signMessage` is the wagmi/viem `useSignMessage` hook exposed as a
 * thunk. It signs the digest above; the server recovers the address
 * and rejects (close 4401) on mismatch or `valid_until` expiry. We mint
 * a five-minute window — long enough that a slow network handshake
 * doesn't race the deadline, short enough that a captured query string
 * can't open a fresh socket later.
 *
 * Phase-3 review MEDIUM: a transient network drop used to leave the
 * ActivityRail stuck on "Disconnected" until the user changed address.
 * `subscribeUserEvents` now reconnects internally with a capped
 * exponential backoff (1s → 30s, ±20% jitter). Each reconnect re-signs
 * the digest — the wallet caches the prompt within the 5-minute window,
 * so users don't see repeated approval popups for a flaky link. The
 * caller's `onStatus("closed")` still fires on the final teardown so
 * the rail can render a sticky error if reconnection is exhausted by
 * an explicit unmount.
 */
export async function subscribeUserEvents(
  user: string,
  signMessage: (_digest: string) => Promise<string>,
  onEvent: (_e: SentinelEvent) => void,
  onStatus?: (_status: "open" | "closed" | "error") => void,
): Promise<() => void> {
  let cancelled = false;
  let attempt = 0;
  let activeWs: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  const _backoffMs = (n: number): number => {
    const base = Math.min(30_000, 1_000 * 2 ** Math.min(n, 5));
    return Math.floor(base * (0.8 + Math.random() * 0.4));
  };

  const _connect = async (): Promise<void> => {
    if (cancelled) return;
    const validUntil = Math.floor(Date.now() / 1000) + 300;
    const digest = wsSubscribeDigest(user, validUntil);
    let signature: string;
    try {
      signature = await signMessage(digest);
    } catch {
      // The user dismissed the wallet prompt — bubble error and stop.
      onStatus?.("error");
      return;
    }
    if (cancelled) return;
    const wsBase = BASE.replace(/^http/, "ws");
    const params = new URLSearchParams({
      valid_until: String(validUntil),
      signature,
    });
    const ws = new WebSocket(`${wsBase}/v1/users/${user}/events?${params.toString()}`);
    activeWs = ws;
    ws.onopen = (): void => {
      attempt = 0;
      onStatus?.("open");
    };
    ws.onmessage = (evt): void => {
      try {
        const data = JSON.parse(evt.data) as SentinelEvent;
        onEvent(data);
      } catch {
        onStatus?.("error");
      }
    };
    ws.onerror = (): void => {
      onStatus?.("error");
    };
    ws.onclose = (): void => {
      activeWs = null;
      if (cancelled) {
        onStatus?.("closed");
        return;
      }
      // Schedule a reconnect; surface "error" while we wait so the
      // rail's ConnDot reflects the gap.
      onStatus?.("error");
      attempt += 1;
      reconnectTimer = setTimeout(() => {
        void _connect();
      }, _backoffMs(attempt));
    };
  };

  await _connect();

  return (): void => {
    cancelled = true;
    if (reconnectTimer != null) clearTimeout(reconnectTimer);
    if (
      activeWs != null
      && (activeWs.readyState === WebSocket.OPEN || activeWs.readyState === WebSocket.CONNECTING)
    ) {
      activeWs.close();
    }
  };
}
