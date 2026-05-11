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

# WS5.B query. Reads the subgraph entities introduced in WS5.B
# (`UserDelegation`, `AllocatorDecision`, `AllocatorReputationUpdate`)
# plus the existing `Allocator` entity. Aggregation is done in the
# Python parser per `project_subgraph_bigint_limitation.md` — graph-ts
# strict-null inference fights BigInt accumulation in mappings, so the
# subgraph emits per-event rows and clients sum them at query time.
#
# Coverage gaps tracked for follow-up:
#   * `aggregate_pnl_above_hwm_e18` — the subgraph does not yet expose
#     per-user net P&L above HWM. WS3.A's per-trade P&L emission will
#     unblock this; for now the parser feeds 0, which collapses the
#     PnL component to 0. Allocators are differentiated on the other
#     three components until that lands.
#   * Breach response timing — `AllocatorDecision` records DEFUND
#     events with the on-chain `reason` string, but pairing each DEFUND
#     with a preceding NAV-drawdown crossover requires walking
#     NAVSnapshot rows the engine already caches. Done as a follow-up
#     in WS7's e2e replay; for now `breach_total_count == 0` so the
#     drawdown component returns 1.0 ("absence of evidence is rewarded"
#     per `docs/reputation-math.md §"Allocator reputation v1"`).
_QUERY_ALLOCATOR_STATE = """
query AllocatorState($windowStart: BigInt!) {
  allocators(first: 1000, where: { stakeAmount_gt: "0" }) {
    id
    stakeAmount
    delegations(first: 1000) {
      capital
      since
      defundedAt
    }
    decisions(
      first: 1000
      where: { timestamp_gte: $windowStart, kind: "DEFUND" }
      orderBy: timestamp
      orderDirection: asc
    ) {
      id
      timestamp
      reason
    }
  }
}
"""
# Filter `stakeAmount_gt: "0"` — the subgraph mapping creates Allocator
# stubs via `loadOrCreate` for any address that appears in adjacent
# events (e.g. the deployer EOA referenced as operator), and those stubs
# have `stakeAmount=0` + `name=""` because `AllocatorRegistered` was
# never emitted for them. Posting reputation for a stub reverts
# `AllocatorNotFound()` from `AllocatorRegistry.updateReputation`
# (the on-chain registry has no entry). Real registered allocators
# always have non-zero stake per `AllocatorRegistry.register`, so this
# is a safe proxy. Belt-and-suspenders: `_parse_allocator` also
# enforces `stake_e18 > 0` for callers that fetch through a different
# code path.

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
    WS5.B subgraph emits per-event rows that the parser sums.

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
        window starting at `window_start_unix`. Allocators don't have a
        single declared class (`AllocatorEntry.supportedClasses` is a
        list per `IAllocatorRegistry`), so `max_stake_in_class_e18` is
        normalized against the global allocator-cohort max stake."""
        if not self._endpoint:
            return []
        resp = await self._client.post(
            self._endpoint,
            json={
                "query": _QUERY_ALLOCATOR_STATE,
                "variables": {"windowStart": str(window_start_unix)},
            },
        )
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        if "errors" in body:
            raise RuntimeError(f"goldsky query errors: {body['errors']}")
        data = body.get("data") or {}
        raw: list[dict[str, Any]] = list(data.get("allocators") or [])
        parsed = [_parse_allocator(a, window_start_unix) for a in raw]
        # Belt-and-suspenders against subgraph stubs that slip past the
        # query filter (e.g. older indexes with mappings that didn't gate
        # `loadOrCreate` on `AllocatorRegistered`). Mirrors the same
        # `stakeAmount > 0` invariant the query enforces.
        parsed = [s for s in parsed if s.stake_e18 > 0]
        max_stake = max((s.stake_e18 for s in parsed), default=0)
        return [
            AllocatorState(
                allocator_id=s.allocator_id,
                declared_class=s.declared_class,
                stake_e18=s.stake_e18,
                max_stake_in_class_e18=max_stake,
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


# Drawdown-defund reasons as emitted by `AllocatorVault.defund` (and any
# permissionless drawdown defund path). Lower-cased substring match so
# the parser is robust to "drawdown threshold breached" phrasings. When
# the on-chain `defund` reason strings stabilize, this can tighten to an
# exact equality check; for now we want to catch any drawdown-flavored
# defund as a breach.
_DRAWDOWN_REASON_TOKENS = ("drawdown", "max_drawdown", "max-drawdown")


def _is_drawdown_reason(reason: str | None) -> bool:
    if not reason:
        return False
    lowered = reason.lower()
    return any(tok in lowered for tok in _DRAWDOWN_REASON_TOKENS)


def _parse_allocator(raw: dict[str, Any], window_start_unix: int) -> AllocatorState:
    delegations: list[dict[str, Any]] = list(raw.get("delegations") or [])
    decisions: list[dict[str, Any]] = list(raw.get("decisions") or [])

    aggregate_capital = 0
    users_at_window_end = 0
    users_at_window_start = 0
    for d in delegations:
        defunded_at = _to_int(d.get("defundedAt"))
        since = _to_int(d.get("since"))
        active = defunded_at == 0
        if active:
            aggregate_capital += _to_int(d.get("capital"))
            users_at_window_end += 1
        # `users_at_window_start`: delegations whose `since <= windowStart`
        # AND were either still active at window start or defunded after
        # window start. A delegation that came and went entirely inside
        # the window is excluded — it cannot contribute to retention by
        # construction.
        if since <= window_start_unix and (defunded_at == 0 or defunded_at > window_start_unix):
            users_at_window_start += 1

    # Breach proxy: count drawdown-flavored DEFUND decisions in the
    # window. Until WS3.A's per-trade P&L emission lands, we cannot
    # pair each breach with a NAV-crossover timestamp, so every
    # observed defund is treated as both a breach AND a response. Net
    # effect: the drawdown component is 1.0 for an allocator that
    # defunded promptly on drawdown reasons, 0/0 (also 1.0) when the
    # window is clean. The placeholder is documented above the query.
    drawdown_defunds = sum(1 for x in decisions if _is_drawdown_reason(x.get("reason")))

    return AllocatorState(
        allocator_id=str(raw.get("id")),
        declared_class="",  # allocators support multiple classes — see fetch_allocator_states
        stake_e18=_to_int(raw.get("stakeAmount")),
        max_stake_in_class_e18=0,  # set by caller
        aggregate_pnl_above_hwm_e18=0,  # WS3.A follow-up — see query header
        aggregate_capital_e18=aggregate_capital,
        breach_total_count=drawdown_defunds,
        breach_response_count=drawdown_defunds,
        users_at_window_start=users_at_window_start,
        users_at_window_end=users_at_window_end,
    )


def _to_int(v: Any) -> int:
    if v is None:
        return 0
    return int(v)
