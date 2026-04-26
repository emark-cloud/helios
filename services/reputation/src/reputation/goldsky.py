"""Thin Goldsky GraphQL client for the reputation engine.

Uses httpx async; only the strategy-rollup query the engine needs in Phase 1.
The query window mirrors `Helios.md §8.2` — 30-day P&L, all-time trade counts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

_QUERY_STRATEGY_ROLLUP = """
query StrategyRollup($since: BigInt!) {
  strategies(first: 1000, where: { active: true }) {
    id
    declaredClass
    currentReputation
    totalAttestedTrades
    totalRealizedPnL
    maxDrawdownBps
    trades(
      first: 1000
      where: { timestamp_gte: $since }
      orderBy: timestamp
      orderDirection: desc
    ) {
      id
      proofValid
      amountIn
      timestamp
    }
    navSnapshots(
      first: 1000
      where: { timestamp_gte: $since }
      orderBy: timestamp
      orderDirection: asc
    ) {
      totalNAV
      timestamp
    }
    allocations(first: 1000) {
      capitalDeployed
      defundedAt
    }
  }
}
"""


@dataclass(frozen=True, slots=True)
class StrategyRollup:
    strategy_id: str
    declared_class: str
    total_attested_trades: int
    total_proof_valid: int
    capital_deployed_e18: int
    realized_pnl_30d_e18: int


class GoldskyClient:
    def __init__(self, endpoint: str, client: httpx.AsyncClient | None = None) -> None:
        self._endpoint = endpoint
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def fetch_strategy_rollups(self, since_unix: int) -> list[StrategyRollup]:
        if not self._endpoint:
            return []
        resp = await self._client.post(
            self._endpoint,
            json={"query": _QUERY_STRATEGY_ROLLUP, "variables": {"since": str(since_unix)}},
        )
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        if "errors" in body:
            raise RuntimeError(f"goldsky query errors: {body['errors']}")
        data = body.get("data") or {}
        strategies: list[dict[str, Any]] = list(data.get("strategies") or [])
        return [_parse_strategy(s) for s in strategies]


def _parse_strategy(raw: dict[str, Any]) -> StrategyRollup:
    trades: list[dict[str, Any]] = list(raw.get("trades") or [])
    nav_snapshots: list[dict[str, Any]] = list(raw.get("navSnapshots") or [])
    allocations: list[dict[str, Any]] = list(raw.get("allocations") or [])

    total_proof_valid = sum(1 for t in trades if t.get("proofValid"))
    capital = _max_int([_to_int(a.get("capitalDeployed")) for a in allocations] or [0])

    realized_pnl = _realized_pnl_30d(nav_snapshots)

    return StrategyRollup(
        strategy_id=str(raw.get("id")),
        declared_class=str(raw.get("declaredClass") or ""),
        total_attested_trades=_to_int(raw.get("totalAttestedTrades")),
        total_proof_valid=total_proof_valid,
        capital_deployed_e18=capital,
        realized_pnl_30d_e18=realized_pnl,
    )


def _to_int(v: Any) -> int:
    if v is None:
        return 0
    return int(v)  # GraphQL BigInt arrives as a string


def _max_int(xs: list[int]) -> int:
    return max(xs) if xs else 0


def _realized_pnl_30d(nav_snapshots: list[dict[str, Any]]) -> int:
    """Latest NAV minus oldest NAV in the window. The subgraph orders ascending
    by timestamp so [0] is oldest and [-1] is newest. Sentinel of 0 when the
    window has fewer than 2 points (no measurable P&L yet)."""
    if len(nav_snapshots) < 2:
        return 0
    return _to_int(nav_snapshots[-1].get("totalNAV")) - _to_int(nav_snapshots[0].get("totalNAV"))
