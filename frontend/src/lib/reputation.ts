/**
 * Reputation Engine HTTP client. Mirrors `services/reputation/src/reputation/service.py`
 * — specifically the `/v1/audit/{actor}` payload that drives the `/audit` page.
 *
 * Helios.md §8.2 — the engine computes the five-component score (performance,
 * risk, proof, stake, age) with cohort-relative Sharpe; this client surfaces
 * the full breakdown so the audit page can render every input the on-chain
 * `componentsHash` commits to.
 */

const BASE = (process.env.NEXT_PUBLIC_REPUTATION_URL ?? "http://localhost:8002").replace(/\/$/, "");

export type CohortStats = {
  size: number;
  median: number;
  iqr: number;
  is_fallback: boolean;
};

export type CohortContext = {
  win_7d: CohortStats;
  win_30d: CohortStats;
  win_90d: CohortStats;
};

export type ScoreComponents = {
  performance: number;
  risk: number;
  proof: number;
  stake: number;
  age: number;
};

export type PerfBreakdown = {
  sharpe_7d: number;
  sharpe_30d: number;
  sharpe_90d: number;
  norm_7d: number;
  norm_30d: number;
  norm_90d: number;
};

export type AuditInputs = {
  stake_e18: string;
  max_stake_in_class_e18: string;
  trades_attested: number;
  max_drawdown_bps_90d: number;
  valid_proofs: number;
  total_proof_attempts: number;
};

export type ComponentWeights = {
  performance: number;
  risk: number;
  proof: number;
  stake: number;
  age: number;
};

export type AuditPayload = {
  actor: string;
  declaredClass: string;
  /** Score scaled to 1e4. Divide by 100 for a 0–100 percentage. */
  score_e4: number;
  components: ScoreComponents;
  components_hash: string;
  perf_breakdown: PerfBreakdown;
  cohort: CohortContext;
  weights: ComponentWeights;
  inputs: AuditInputs;
};

export class ReputationError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ReputationError";
    this.status = status;
  }
}

async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${BASE}/v1${path}`, { signal });
  if (!res.ok) throw new ReputationError(`Reputation HTTP ${res.status}`, res.status);
  return (await res.json()) as T;
}

export function fetchAuditForActor(actor: string, signal?: AbortSignal): Promise<AuditPayload> {
  return request<AuditPayload>(`/audit/${actor}`, signal);
}
