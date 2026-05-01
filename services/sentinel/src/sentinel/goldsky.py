"""Sentinel's Goldsky reads.

The reputation engine uses Goldsky for its score computation; Sentinel
uses it to *consume* those scores (latest reputation per strategy) plus
the strategy directory entries (registered strategies, their declared
class, fee rate, capacity, current allocations).

Phase 1 is offline-tolerant: when `GOLDSKY_ENDPOINT` is unset, methods
return empty lists rather than raising. This matches reputation's
posture and lets the loop run in scenario mode without an indexer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from helios_allocator.types import StrategyCandidate

_QUERY_DIRECTORY = """
query StrategyDirectory {
  strategies(first: 200, where: { active: true }) {
    id
    declaredClass
    operator
    feeRateBps
    stakeAmount
    maxCapacity
    currentReputation
    totalAttestedTrades
    allocations(first: 200, where: { defundedAt: 0 }) {
      capitalDeployed
    }
  }
}
"""


@dataclass(frozen=True, slots=True)
class StrategyDirectoryRow:
    strategy_id: str
    declared_class: str
    chain_id: int
    operator: str
    fee_rate_bps: int
    stake_amount_usd: int
    max_capacity_usd: int
    current_allocations_usd: int
    reputation_score_e4: int
    trades_attested: int = 0


class SentinelGoldsky:
    def __init__(
        self,
        endpoint: str,
        chain_id: int,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._chain_id = chain_id
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def fetch_directory(self) -> list[StrategyDirectoryRow]:
        if not self._endpoint:
            return []
        resp = await self._client.post(self._endpoint, json={"query": _QUERY_DIRECTORY})
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        if "errors" in body:
            raise RuntimeError(f"goldsky errors: {body['errors']}")
        rows: list[dict[str, Any]] = list((body.get("data") or {}).get("strategies") or [])
        return [self._parse(r) for r in rows]

    async def fetch_candidates(self) -> list[StrategyCandidate]:
        rows = await self.fetch_directory()
        return [_to_candidate(r) for r in rows]

    def _parse(self, raw: dict[str, Any]) -> StrategyDirectoryRow:
        allocs = list(raw.get("allocations") or [])
        # `Allocation.capitalDeployed` is per-event (graph-ts BigInt limitation,
        # see project_subgraph_bigint_limitation.md). Sum at query time.
        deployed = sum(_to_int(a.get("capitalDeployed")) for a in allocs)
        return StrategyDirectoryRow(
            strategy_id=str(raw.get("id")),
            declared_class=str(raw.get("declaredClass") or ""),
            chain_id=self._chain_id,
            operator=str(raw.get("operator") or "0x" + "0" * 40),
            fee_rate_bps=_to_int(raw.get("feeRateBps")),
            stake_amount_usd=_to_int(raw.get("stakeAmount")),
            max_capacity_usd=_to_int(raw.get("maxCapacity")),
            current_allocations_usd=deployed,
            reputation_score_e4=_to_int(raw.get("currentReputation")),
            trades_attested=_to_int(raw.get("totalAttestedTrades")),
        )


def _to_candidate(row: StrategyDirectoryRow) -> StrategyCandidate:
    # `currentReputation` is stored as score_e4 (signed int, -10_000..+10_000)
    # — convert to a [0, 1] float for the allocator's ranking math. Negative
    # scores become 0 (we don't allocate to provably bad strategies).
    rep_float = max(0.0, row.reputation_score_e4 / 10_000.0)
    return StrategyCandidate(
        strategy_id=row.strategy_id,
        declared_class=row.declared_class,
        chain_id=row.chain_id,
        operator=row.operator,
        fee_rate_bps=row.fee_rate_bps,
        stake_amount_usd=row.stake_amount_usd,
        max_capacity_usd=row.max_capacity_usd,
        current_allocations_usd=row.current_allocations_usd,
        reputation_score=rep_float,
        trades_attested=row.trades_attested,
    )


def _to_int(v: Any) -> int:
    if v is None:
        return 0
    return int(v)
