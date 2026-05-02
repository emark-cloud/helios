"""Goldsky GraphQL client for the reputation engine.

Phase 2 (`Helios.md §8.2`) needs raw per-trade and NAV events to compute
windowed Sharpe and 90d drawdown. The query pulls a 90d window — the engine
slices into 7d/30d/90d via `reputation.windows`.

Honors the no-schema-bump rule (`project_subgraph_goldsky_wasm`): all data
extracted from existing entities (`Trade`, `NAVSnapshot`, `Allocation`,
`Strategy`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

_QUERY_STRATEGY_STATE = """
query StrategyState($since: BigInt!) {
  strategies(first: 1000, where: { active: true }) {
    id
    declaredClass
    stakeAmount
    currentReputation
    totalAttestedTrades
    totalRealizedPnL
    maxDrawdownBps
    trades(
      first: 1000
      where: { timestamp_gte: $since }
      orderBy: timestamp
      orderDirection: asc
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
    paramsRotations(
      first: 100
      orderBy: timestamp
      orderDirection: desc
    ) {
      timestamp
    }
  }
}
"""


@dataclass(frozen=True, slots=True)
class TradeEvent:
    timestamp: int
    proof_valid: bool
    amount_in_e18: int


@dataclass(frozen=True, slots=True)
class NavEvent:
    timestamp: int
    total_nav_e18: int


@dataclass(frozen=True, slots=True)
class StrategyState:
    """Raw 90d state for one strategy. Engine slices and aggregates."""

    strategy_id: str
    declared_class: str
    stake_e18: int
    trades_attested: int  # lifetime
    capital_deployed_e18: int  # current, summed across allocation events
    trades_90d: list[TradeEvent]
    nav_snapshots_90d: list[NavEvent]
    # WS7.A: unix-second timestamp of the most recent
    # `StrategyRegistry.ParamsRotated` event for this strategy. The
    # engine resets the AgeScore + PerformanceScore windows to start
    # at this epoch (track-record breaks visibly across rotations).
    # Risk + proof are unaffected so a strategy can't escape its
    # drawdown / proof history by rotating params. 0 = never rotated.
    last_rotation_epoch: int = 0


class GoldskyClient:
    def __init__(self, endpoint: str, client: httpx.AsyncClient | None = None) -> None:
        self._endpoint = endpoint
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def fetch_strategy_states(self, since_unix: int) -> list[StrategyState]:
        if not self._endpoint:
            return []
        resp = await self._client.post(
            self._endpoint,
            json={"query": _QUERY_STRATEGY_STATE, "variables": {"since": str(since_unix)}},
        )
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        if "errors" in body:
            raise RuntimeError(f"goldsky query errors: {body['errors']}")
        data = body.get("data") or {}
        strategies: list[dict[str, Any]] = list(data.get("strategies") or [])
        return [_parse_strategy(s) for s in strategies]


def _parse_strategy(raw: dict[str, Any]) -> StrategyState:
    trades_raw: list[dict[str, Any]] = list(raw.get("trades") or [])
    nav_raw: list[dict[str, Any]] = list(raw.get("navSnapshots") or [])
    allocations: list[dict[str, Any]] = list(raw.get("allocations") or [])

    trades = [
        TradeEvent(
            timestamp=_to_int(t.get("timestamp")),
            proof_valid=bool(t.get("proofValid")),
            amount_in_e18=_to_int(t.get("amountIn")),
        )
        for t in trades_raw
    ]
    nav = [
        NavEvent(
            timestamp=_to_int(n.get("timestamp")),
            total_nav_e18=_to_int(n.get("totalNAV")),
        )
        for n in nav_raw
    ]

    # `Allocation.capitalDeployed` is per-event (graph-ts BigInt limitation,
    # see project_subgraph_bigint_limitation.md). Sum at query time, ignoring
    # defunded allocations so capital reflects live exposure only.
    capital = sum(
        _to_int(a.get("capitalDeployed"))
        for a in allocations
        if a.get("defundedAt") in (None, "0", 0)
    )

    rotations: list[dict[str, Any]] = list(raw.get("paramsRotations") or [])
    # Query orders by timestamp desc — first row is the most recent. 0 if none.
    last_rotation = _to_int(rotations[0].get("timestamp")) if rotations else 0

    return StrategyState(
        strategy_id=str(raw.get("id")),
        declared_class=str(raw.get("declaredClass") or ""),
        stake_e18=_to_int(raw.get("stakeAmount")),
        trades_attested=_to_int(raw.get("totalAttestedTrades")),
        capital_deployed_e18=capital,
        trades_90d=trades,
        nav_snapshots_90d=nav,
        last_rotation_epoch=last_rotation,
    )


def _to_int(v: Any) -> int:
    if v is None:
        return 0
    return int(v)
