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

# WS5.A: forward-looking query against the entities WS5.B (subgraph allocator
# entities) will land. The Goldsky schema fields below mirror the planned
# `Allocator` / `UserDelegation` / `AllocatorDecision` entities. Until WS5.B
# ships, this query errors against the live subgraph; engine + tests run
# against stubs that pre-aggregate `AllocatorState` directly.
#
# Per `project_subgraph_bigint_limitation.md`, mapping handlers cannot
# accumulate BigInt without graph-ts strict-null fights, so the parser
# below sums per-event rows at query time — same posture as the strategy
# `Allocation.capitalDeployed` aggregation.
_QUERY_ALLOCATOR_STATE = """
query AllocatorState($since: BigInt!, $windowStart: BigInt!) {
  allocators(first: 1000) {
    id
    stakeAmount
    declaredClass
    delegations(first: 1000) {
      capital
      pnlAboveHwm
      since
      defundedAt
    }
    breaches: decisions(
      first: 1000
      where: { timestamp_gte: $windowStart, kind: BREACH }
      orderBy: timestamp
      orderDirection: asc
    ) {
      id
      timestamp
      defundedAt
    }
  }
}
"""

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


@dataclass(frozen=True, slots=True)
class AllocatorState:
    """Pre-aggregated 30d allocator state. Goldsky-side aggregation is done
    in `_parse_allocator` rather than the WASM mapping handlers — the
    WS5.A query returns per-event rows that the parser sums.

    Fields drive the four-component formula in `score.compute_allocator_score`:

    - `aggregate_pnl_above_hwm_e18` (signed) — Σ user net P&L above HWM,
      across active delegations. Dominant factor (`Helios.md §8` allocator
      scoring; weights documented in `docs/reputation-math.md`).
    - `aggregate_capital_e18` — Σ capital under management, used to
      normalize P&L into a [-1, 1] component.
    - `breach_total_count` / `breach_response_count` — drawdown discipline
      ratio. A breach is "responded" when the allocator defunded the
      affected user within `DRAWDOWN_RESPONSE_SEC` (60s) of the breach.
    - `users_at_window_start` / `users_at_window_end` — 30d retention
      ratio (inverted churn).
    - `stake_e18` / `max_stake_in_class_e18` — same log curve as strategies
      (`Helios.md §8.2 StakeScore`).
    """

    allocator_id: str
    declared_class: str
    stake_e18: int
    max_stake_in_class_e18: int
    aggregate_pnl_above_hwm_e18: int
    aggregate_capital_e18: int
    breach_total_count: int
    breach_response_count: int
    users_at_window_start: int
    users_at_window_end: int


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

    async def fetch_allocator_states(self, window_start_unix: int) -> list[AllocatorState]:
        """Fetch per-allocator pre-aggregated state for the 30d retention
        window starting at `window_start_unix`. The class-relative
        `max_stake_in_class_e18` is filled in here (not in the subgraph)
        from the response itself."""
        if not self._endpoint:
            return []
        # `since` carries the same value (parser uses it for breach
        # filtering), kept as a separate variable for future flexibility
        # if the breach window diverges from the retention window.
        resp = await self._client.post(
            self._endpoint,
            json={
                "query": _QUERY_ALLOCATOR_STATE,
                "variables": {
                    "since": str(window_start_unix),
                    "windowStart": str(window_start_unix),
                },
            },
        )
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        if "errors" in body:
            raise RuntimeError(f"goldsky query errors: {body['errors']}")
        data = body.get("data") or {}
        raw: list[dict[str, Any]] = list(data.get("allocators") or [])
        parsed = [_parse_allocator(a, window_start_unix) for a in raw]
        # Class-relative max stake is computed across the response so the
        # stake component is bounded on the live cohort, not historical.
        max_stake_by_class: dict[str, int] = {}
        for s in parsed:
            cur = max_stake_by_class.get(s.declared_class, 0)
            if s.stake_e18 > cur:
                max_stake_by_class[s.declared_class] = s.stake_e18
        return [
            AllocatorState(
                allocator_id=s.allocator_id,
                declared_class=s.declared_class,
                stake_e18=s.stake_e18,
                max_stake_in_class_e18=max_stake_by_class.get(s.declared_class, 0),
                aggregate_pnl_above_hwm_e18=s.aggregate_pnl_above_hwm_e18,
                aggregate_capital_e18=s.aggregate_capital_e18,
                breach_total_count=s.breach_total_count,
                breach_response_count=s.breach_response_count,
                users_at_window_start=s.users_at_window_start,
                users_at_window_end=s.users_at_window_end,
            )
            for s in parsed
        ]


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


# Allocator drawdown-discipline window: a breach is "responded" if the
# allocator defunded the affected user within this many seconds. 60s
# matches the spec callout in `docs/phase3-plan.md` WS5.A.
_DRAWDOWN_RESPONSE_SEC = 60


def _parse_allocator(raw: dict[str, Any], window_start_unix: int) -> AllocatorState:
    delegations: list[dict[str, Any]] = list(raw.get("delegations") or [])
    breaches: list[dict[str, Any]] = list(raw.get("breaches") or [])

    # Aggregate P&L + capital across delegations, ignoring defunded ones
    # (capital is no longer at work for this allocator). Same posture as
    # the strategy `Allocation.capitalDeployed` filter.
    aggregate_pnl = 0
    aggregate_capital = 0
    users_at_window_end = 0
    users_at_window_start = 0
    for d in delegations:
        defunded_at = _to_int(d.get("defundedAt"))
        since = _to_int(d.get("since"))
        active = defunded_at == 0
        if active:
            aggregate_capital += _to_int(d.get("capital"))
            aggregate_pnl += _to_int(d.get("pnlAboveHwm"))
            users_at_window_end += 1
        # `users_at_window_start`: delegations whose `since <= windowStart`
        # AND were either still active at window start or defunded after
        # window start. A delegation that came and went entirely inside
        # the window is excluded — it cannot contribute to retention by
        # construction.
        if since <= window_start_unix and (defunded_at == 0 or defunded_at > window_start_unix):
            users_at_window_start += 1

    # Breach response: defunded within 60s of breach. `breaches` already
    # filtered to the window by the GraphQL `where` clause.
    breach_total_count = len(breaches)
    breach_response_count = 0
    for b in breaches:
        breach_ts = _to_int(b.get("timestamp"))
        defunded_at = _to_int(b.get("defundedAt"))
        if defunded_at > 0 and (defunded_at - breach_ts) <= _DRAWDOWN_RESPONSE_SEC:
            breach_response_count += 1

    return AllocatorState(
        allocator_id=str(raw.get("id")),
        declared_class=str(raw.get("declaredClass") or ""),
        stake_e18=_to_int(raw.get("stakeAmount")),
        max_stake_in_class_e18=0,  # set by caller
        aggregate_pnl_above_hwm_e18=aggregate_pnl,
        aggregate_capital_e18=aggregate_capital,
        breach_total_count=breach_total_count,
        breach_response_count=breach_response_count,
        users_at_window_start=users_at_window_start,
        users_at_window_end=users_at_window_end,
    )


def _to_int(v: Any) -> int:
    if v is None:
        return 0
    return int(v)
