"""AllocatorGoldsky — strategy directory + reputation reads.

The reputation engine uses Goldsky for its score computation; the
allocator uses it to *consume* those scores (latest reputation per
strategy) plus the strategy directory entries (registered strategies,
their declared class, fee rate, capacity, current allocations).

Offline-tolerant: when `endpoint` is unset, methods return empty lists
rather than raising. This matches reputation's posture and lets the
loop run in scenario mode without an indexer.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from helios_allocator.types import StrategyCandidate

_log = structlog.get_logger(__name__)

# Frontend POSTs allowed_strategy_classes as slugs; Goldsky surfaces
# `declaredClass` as the on-chain Poseidon hash. Cache the reverse
# lookup at import time so `_normalise_class` stays a hot-path lookup
# without redoing the bytes→hex conversion on every directory refresh.
try:
    from helios_contracts_abi.class_ids import BYTES32_TO_SLUG as _BYTES32_TO_SLUG
except ImportError:  # pragma: no cover — workspace-only fallback
    _BYTES32_TO_SLUG: dict[bytes, str] = {}

_QUERY_DIRECTORY = """
query StrategyDirectory {
  strategies(first: 200, where: { active: true }) {
    id
    declaredClass
    chainId
    operator
    feeRateBps
    stakeAmount
    maxCapacity
    currentReputation
    totalAttestedTrades
    allocations(first: 200, where: { defundedAt: 0 }) {
      capitalDeployed
    }
    navSnapshots(first: 1, orderBy: timestamp, orderDirection: desc) {
      timestamp
    }
  }
}
"""


# Map each chain to the decimals of its mUSDC base asset. Subgraphs index
# raw on-chain values (e.g. stakeAmount in baseAsset wei), so a Base/Arb
# vault with 6-dec mUSDC surfaces a stake of 5000e6 while a Kite vault
# with 18-dec mUSDC surfaces 5000e18 for the same nominal exposure. The
# allocator's bootstrap pool weights by stake — without normalization,
# remote candidates get ~3.3e-13 of the share that Kite candidates do,
# producing a dust amount that fails the OFT adapter's sharedDecimals
# guard with `SlippageExceeded`. Project all *_usd fields onto a 18-dec
# canonical wei base so a 5000 mUSDC stake reads as 5000e18 regardless
# of which chain hosts the vault.
_CANONICAL_DECIMALS = 18
_BASE_ASSET_DECIMALS_BY_CHAIN: dict[int, int] = {
    2368: 18,  # Kite testnet — mUSDC mock at 18-dec
    2366: 18,  # Kite mainnet (stretch) — same convention
    84_532: 6,  # Base Sepolia mUSDC
    421_614: 6,  # Arbitrum Sepolia mUSDC
}


def _canonical_scale_for(chain_id: int) -> int:
    """Return the multiplier that scales `chain_id`'s base-asset wei to
    the 18-dec canonical base. Unknown chains default to 1 (no scaling
    — safer than guessing a decimal mismatch into existence)."""
    src = _BASE_ASSET_DECIMALS_BY_CHAIN.get(chain_id, _CANONICAL_DECIMALS)
    return 10 ** (_CANONICAL_DECIMALS - src) if src <= _CANONICAL_DECIMALS else 1


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
    # Unix-seconds timestamp of the most recent on-chain NAV snapshot
    # for this strategy, or 0 if the strategy has never NAV-reported.
    # Allocators use this to gate cold-start allocations on whether
    # an operator is actively driving the vault — a strategy whose
    # navOracle key is offline shouldn't receive capital just because
    # its registry row is `active=true`.
    last_nav_update_ts: int = 0


class AllocatorGoldsky:
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
        return [to_candidate(r) for r in rows]

    def _parse(self, raw: dict[str, Any]) -> StrategyDirectoryRow:
        allocs = list(raw.get("allocations") or [])
        # `Allocation.capitalDeployed` is per-event (graph-ts BigInt limitation,
        # see project_subgraph_bigint_limitation.md). Sum at query time.
        deployed = sum(_to_int(a.get("capitalDeployed")) for a in allocs)
        snaps = list(raw.get("navSnapshots") or [])
        last_nav_ts = _to_int(snaps[0].get("timestamp")) if snaps else 0
        # CXR-4 (2026-05-13) — read chainId from Goldsky when present so a
        # multi-chain fan-out (future Phase-2 work) returns rows tagged
        # with each strategy's actual execution chain. Falls back to the
        # constructor's chain id on legacy indexes where `chainId` is 0
        # or missing (Kite v0.7.2 still ships pre-CXR-4 `getOrCreateStrategy`
        # which initializes chainId=0 for Trade-bootstrapped strategies).
        raw_chain_id = _to_int(raw.get("chainId"))
        chain_id = raw_chain_id if raw_chain_id > 0 else self._chain_id
        # Normalize *_usd fields to 18-dec canonical wei so a 6-dec Base/Arb
        # vault's stake compares apples-to-apples with an 18-dec Kite vault.
        # Without this, bootstrap stake-weighting collapses remote candidates
        # to dust and `allocateToRemoteStrategy` reverts SlippageExceeded.
        scale = _canonical_scale_for(chain_id)
        return StrategyDirectoryRow(
            strategy_id=str(raw.get("id")),
            declared_class=str(raw.get("declaredClass") or ""),
            chain_id=chain_id,
            operator=str(raw.get("operator") or "0x" + "0" * 40),
            fee_rate_bps=_to_int(raw.get("feeRateBps")),
            stake_amount_usd=_to_int(raw.get("stakeAmount")) * scale,
            max_capacity_usd=_to_int(raw.get("maxCapacity")) * scale,
            current_allocations_usd=deployed * scale,
            reputation_score_e4=_to_int(raw.get("currentReputation")),
            trades_attested=_to_int(raw.get("totalAttestedTrades")),
            last_nav_update_ts=last_nav_ts,
        )


def to_candidate(row: StrategyDirectoryRow) -> StrategyCandidate:
    """Convert a `StrategyDirectoryRow` into a candidate consumable by
    `BaseAllocator.rank_strategies`. Public so allocator authors can map
    custom directory sources (CSV, alt indexer) without re-implementing
    the score-e4 → float convention.

    `currentReputation` is stored as score_e4 (signed int, -10_000..+10_000)
    — convert to a [0, 1] float for the allocator's ranking math. Negative
    scores become 0 (we don't allocate to provably bad strategies).

    Goldsky exposes `declaredClass` as the on-chain Poseidon hash
    (`0x2a9aa442…`), but `MetaStrategy.allowed_strategy_classes` is the
    human-readable slug list (`["momentum_v1", …]`) the frontend POSTs.
    Normalise hash → slug here so `StrategyCandidate.class_fit` sees
    matching identifiers; orphan classes that aren't in `BYTES32_TO_SLUG`
    keep their raw hash and naturally score 0.
    """
    rep_float = max(0.0, row.reputation_score_e4 / 10_000.0)
    return StrategyCandidate(
        strategy_id=row.strategy_id,
        declared_class=_normalise_class(row.declared_class),
        chain_id=row.chain_id,
        operator=row.operator,
        fee_rate_bps=row.fee_rate_bps,
        stake_amount_usd=row.stake_amount_usd,
        max_capacity_usd=row.max_capacity_usd,
        current_allocations_usd=row.current_allocations_usd,
        reputation_score=rep_float,
        trades_attested=row.trades_attested,
    )


def _normalise_class(declared: str) -> str:
    """Map a Poseidon hash hex (with or without 0x prefix) back to its
    canonical slug from `helios_contracts_abi.class_ids`. Falls back to
    the raw input on any failure so unknown classes still surface in
    /v1/strategies — they just won't pick up allocator score because
    `class_fit` won't match the slug-keyed `allowed_strategy_classes`.
    """
    if not declared:
        return declared
    try:
        h = declared[2:] if declared.startswith("0x") else declared
        return _BYTES32_TO_SLUG.get(bytes.fromhex(h), declared)
    except ValueError:
        return declared


def _to_int(v: Any) -> int:
    if v is None:
        return 0
    return int(v)


class MultiChainAllocatorGoldsky:
    """Fan `fetch_directory()` out across one Goldsky endpoint per chain
    and merge the rows. Per Helios.md §12.1, strategies execute on the
    chain whose venue best fits their class (mom/mr on Base for deep
    Uniswap V3 liquidity, yr on Arbitrum for Aave). Each chain has its
    own subgraph deployment (`helios/v0.9.0`, `helios-base/v0.9.0`,
    `helios-arbitrum/v0.9.0` — venue subgraphs redeployed to v0.9.0
    2026-05-17 after the v0.8.0 deployments 404'd) — Sentinel/Helix
    need to see all three to rank the full multi-chain candidate set.

    Each constituent `AllocatorGoldsky` keeps its own `chain_id`. The
    merger drops rows whose `chain_id` doesn't match the source endpoint
    so a misconfigured fan-out can't smuggle a Kite strategy into the
    Base candidate set. Duplicate `strategy_id` collisions across chains
    (theoretically possible if two registries happened to assign the
    same id) keep the first row seen — deterministic ordering follows
    the constructor's source list.

    Same offline-tolerant posture as `AllocatorGoldsky`: a source with
    an empty endpoint returns []; a source that raises is logged and
    skipped so a single broken endpoint can't take down the whole
    candidate refresh.
    """

    def __init__(
        self,
        sources: list[AllocatorGoldsky],
    ) -> None:
        if not sources:
            raise ValueError("MultiChainAllocatorGoldsky requires ≥1 source")
        self._sources = sources

    @classmethod
    def from_endpoints(
        cls,
        endpoints_by_chain: dict[int, str],
        client: httpx.AsyncClient | None = None,
    ) -> MultiChainAllocatorGoldsky:
        """Build a multi-chain client from a `{chain_id: endpoint_url}`
        mapping. Empty / falsy endpoint values are dropped — a service
        with only `GOLDSKY_ENDPOINT` set still gets a single-source
        fan-out that behaves identically to the original
        `AllocatorGoldsky`.

        When `client` is given, all sources share it (cheaper TCP reuse
        for the common case where the three endpoints sit behind the
        same Goldsky CDN). When omitted, each source owns its own
        `httpx.AsyncClient`.
        """
        sources: list[AllocatorGoldsky] = []
        for chain_id, endpoint in endpoints_by_chain.items():
            if not endpoint:
                continue
            sources.append(AllocatorGoldsky(endpoint=endpoint, chain_id=chain_id, client=client))
        if not sources:
            # Preserve the offline-tolerant posture — if all endpoints
            # are blank, hand back a one-source wrapper pointed at the
            # empty Kite endpoint so `fetch_directory()` returns []
            # rather than raising.
            sources.append(AllocatorGoldsky(endpoint="", chain_id=0, client=client))
        return cls(sources=sources)

    async def aclose(self) -> None:
        for src in self._sources:
            await src.aclose()

    async def fetch_directory(self) -> list[StrategyDirectoryRow]:
        """Fan out across every source concurrently and merge. Rows whose
        Goldsky-reported `chain_id` doesn't match the source endpoint's
        chain are dropped (defensive: a fresh chain whose subgraph still
        ships pre-CXR-4 mappings would emit `chainId=0` and inherit the
        source's chain id via `AllocatorGoldsky._parse`, which is fine —
        but a Kite strategy surfaced from the Base endpoint via a
        misconfigured indexer would be dropped here)."""
        results = await asyncio.gather(
            *(src.fetch_directory() for src in self._sources),
            return_exceptions=True,
        )
        merged: list[StrategyDirectoryRow] = []
        seen: set[str] = set()
        for src, result in zip(self._sources, results, strict=True):
            if isinstance(result, BaseException):
                _log.warning(
                    "allocator.goldsky.fan_out_source_failed",
                    chain_id=src._chain_id,
                    err=str(result),
                )
                continue
            for row in result:
                if src._chain_id > 0 and row.chain_id != src._chain_id:
                    # Source chain mismatch — drop. The source endpoint
                    # is the authoritative chain tag; trusting the row
                    # would allow a misconfigured subgraph to pollute
                    # the candidate set across chains.
                    continue
                if row.strategy_id in seen:
                    continue
                seen.add(row.strategy_id)
                merged.append(row)
        return merged

    async def fetch_candidates(self) -> list[StrategyCandidate]:
        rows = await self.fetch_directory()
        return [to_candidate(r) for r in rows]


__all__ = [
    "AllocatorGoldsky",
    "MultiChainAllocatorGoldsky",
    "StrategyDirectoryRow",
    "to_candidate",
]
