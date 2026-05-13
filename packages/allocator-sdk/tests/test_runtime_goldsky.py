"""Smoke tests for `AllocatorGoldsky` directory parsing.

Live HTTP integration runs against the live Goldsky endpoint via the
deployed allocator services. Here we only need: the offline-tolerant
path returns []; the parse + candidate-mapping logic produces the
expected shape.
"""

from __future__ import annotations

from typing import Any

import pytest
from helios_allocator.runtime.goldsky import (
    AllocatorGoldsky,
    MultiChainAllocatorGoldsky,
    StrategyDirectoryRow,
    to_candidate,
)
from helios_allocator.types import StrategyCandidate


@pytest.mark.asyncio
async def test_empty_endpoint_returns_no_rows() -> None:
    g = AllocatorGoldsky(endpoint="", chain_id=2368)
    assert await g.fetch_directory() == []
    assert await g.fetch_candidates() == []
    await g.aclose()


def test_to_candidate_clamps_negative_reputation() -> None:
    """Negative reputation must clamp to 0 — we don't allocate to provably
    bad strategies even if their score has gone red."""
    row = StrategyDirectoryRow(
        strategy_id="0x" + "11" * 20,
        declared_class="momentum_v1",
        chain_id=2368,
        operator="0x" + "cc" * 20,
        fee_rate_bps=1_000,
        stake_amount_usd=5_000,
        max_capacity_usd=100_000,
        current_allocations_usd=10_000,
        reputation_score_e4=-2_500,
        trades_attested=42,
    )
    candidate = to_candidate(row)
    assert isinstance(candidate, StrategyCandidate)
    assert candidate.reputation_score == 0.0
    assert candidate.trades_attested == 42


def test_to_candidate_normalises_poseidon_hash_to_slug() -> None:
    """Goldsky surfaces `declaredClass` as the on-chain Poseidon hash, but
    `MetaStrategy.allowed_strategy_classes` is a slug list (the frontend
    POSTs `["momentum_v1", …]`). Unless `to_candidate` normalises hash
    → slug, every `class_fit` lookup returns 0 and the allocator's
    score collapses to 0 across the board — i.e. an exact repro of the
    'no allocations ever fire' production silence we hit on Kite testnet
    after the v0.6.0 cutover."""

    momentum_v1_hash = "0x2a9aa442064b635baec37a7a259282faa5563a653a8325378d5676c6f04bc9dd"
    row = StrategyDirectoryRow(
        strategy_id="0x" + "44" * 20,
        declared_class=momentum_v1_hash,
        chain_id=2368,
        operator="0x" + "ff" * 20,
        fee_rate_bps=1_000,
        stake_amount_usd=5_000,
        max_capacity_usd=100_000,
        current_allocations_usd=0,
        reputation_score_e4=8_000,
        trades_attested=120,
    )
    candidate = to_candidate(row)
    assert candidate.declared_class == "momentum_v1"
    assert candidate.class_fit(["momentum_v1"]) == 1.0
    assert candidate.class_fit(["mean_reversion_v1"]) == 0.0


def test_to_candidate_keeps_unknown_class_hash_as_is() -> None:
    """Orphan strategies registered outside the canonical class set must
    still flow through the directory — they just won't earn allocator
    score because their hash won't match any user's slug list. Keeps
    `/v1/strategies` honest about the on-chain registry without
    silently dropping rows."""

    row = StrategyDirectoryRow(
        strategy_id="0x" + "55" * 20,
        declared_class="0xdeadbeef" + "00" * 28,
        chain_id=2368,
        operator="0x" + "ff" * 20,
        fee_rate_bps=1_000,
        stake_amount_usd=0,
        max_capacity_usd=0,
        current_allocations_usd=0,
        reputation_score_e4=0,
        trades_attested=0,
    )
    candidate = to_candidate(row)
    assert candidate.declared_class.startswith("0xdeadbeef")
    assert candidate.class_fit(["momentum_v1"]) == 0.0


def test_to_candidate_scales_e4_to_unit_float() -> None:
    row = StrategyDirectoryRow(
        strategy_id="0x" + "22" * 20,
        declared_class="mean_reversion_v1",
        chain_id=2368,
        operator="0x" + "dd" * 20,
        fee_rate_bps=500,
        stake_amount_usd=20_000,
        max_capacity_usd=200_000,
        current_allocations_usd=50_000,
        reputation_score_e4=7_500,
        trades_attested=100,
    )
    candidate = to_candidate(row)
    assert candidate.reputation_score == pytest.approx(0.75)
    assert candidate.declared_class == "mean_reversion_v1"
    assert candidate.fee_rate_bps == 500


# ── MultiChainAllocatorGoldsky ────────────────────────────────


class _FakeSource:
    """Drop-in stand-in for `AllocatorGoldsky` that returns canned rows
    or raises on `fetch_directory()`. Keeps the multi-chain fan-out
    tests offline (the real class is HTTP-bound via httpx)."""

    def __init__(self, chain_id: int, rows: list[StrategyDirectoryRow], *, fail: bool = False):
        self._chain_id = chain_id
        self._rows = rows
        self._fail = fail
        self.closed = False

    async def fetch_directory(self) -> list[StrategyDirectoryRow]:
        if self._fail:
            raise RuntimeError("simulated source failure")
        return list(self._rows)

    async def fetch_candidates(self) -> list[StrategyCandidate]:
        return [to_candidate(r) for r in await self.fetch_directory()]

    async def aclose(self) -> None:
        self.closed = True


def _row(strategy_id: str, chain_id: int) -> StrategyDirectoryRow:
    return StrategyDirectoryRow(
        strategy_id=strategy_id,
        declared_class="momentum_v1",
        chain_id=chain_id,
        operator="0x" + "aa" * 20,
        fee_rate_bps=1_000,
        stake_amount_usd=5_000,
        max_capacity_usd=100_000,
        current_allocations_usd=0,
        reputation_score_e4=8_000,
        trades_attested=10,
    )


@pytest.mark.asyncio
async def test_multichain_merges_rows_by_strategy_id() -> None:
    """The fan-out preserves per-chain rows and tags each by source."""
    kite_row = _row("0x" + "11" * 20, 2368)
    base_row = _row("0x" + "22" * 20, 84_532)
    arb_row = _row("0x" + "33" * 20, 421_614)

    mc = MultiChainAllocatorGoldsky(
        sources=[
            _FakeSource(2368, [kite_row]),  # type: ignore[list-item]
            _FakeSource(84_532, [base_row]),  # type: ignore[list-item]
            _FakeSource(421_614, [arb_row]),  # type: ignore[list-item]
        ]
    )
    merged = await mc.fetch_directory()
    assert {r.strategy_id for r in merged} == {
        kite_row.strategy_id,
        base_row.strategy_id,
        arb_row.strategy_id,
    }
    assert {r.chain_id for r in merged} == {2368, 84_532, 421_614}


@pytest.mark.asyncio
async def test_multichain_drops_cross_chain_pollution() -> None:
    """A source claiming to be `chain_id=2368` that returns a row with
    `chain_id=84_532` (e.g., misconfigured subgraph index) gets the
    rogue row dropped — the source endpoint is the authoritative chain
    tag. Without this guard a Base entry mis-published on the Kite
    subgraph would pollute the candidate set."""
    rogue_kite_row = _row("0x" + "99" * 20, 84_532)  # claims chain 84_532
    real_kite_row = _row("0x" + "11" * 20, 2368)

    mc = MultiChainAllocatorGoldsky(
        sources=[
            _FakeSource(2368, [rogue_kite_row, real_kite_row]),  # type: ignore[list-item]
        ]
    )
    merged = await mc.fetch_directory()
    assert [r.strategy_id for r in merged] == [real_kite_row.strategy_id]


@pytest.mark.asyncio
async def test_multichain_one_source_failure_doesnt_take_down_others() -> None:
    """A 5xx from Goldsky on one chain must not blank the candidate
    set — the loop still rebalances against the chains that responded.
    Mirrors the offline-tolerant posture of single-source
    `AllocatorGoldsky.fetch_directory`."""
    base_row = _row("0x" + "22" * 20, 84_532)
    mc = MultiChainAllocatorGoldsky(
        sources=[
            _FakeSource(2368, [], fail=True),  # type: ignore[list-item]
            _FakeSource(84_532, [base_row]),  # type: ignore[list-item]
        ]
    )
    merged = await mc.fetch_directory()
    assert [r.strategy_id for r in merged] == [base_row.strategy_id]


@pytest.mark.asyncio
async def test_multichain_dedups_by_strategy_id_first_seen() -> None:
    """Belt-and-braces against the theoretical case where two registries
    happened to assign the same strategy id (unlikely but possible
    given paramsHash collisions). The first source wins so ordering is
    deterministic."""
    duplicate_id = "0x" + "11" * 20
    mc = MultiChainAllocatorGoldsky(
        sources=[
            _FakeSource(2368, [_row(duplicate_id, 2368)]),  # type: ignore[list-item]
            _FakeSource(84_532, [_row(duplicate_id, 84_532)]),  # type: ignore[list-item]
        ]
    )
    merged = await mc.fetch_directory()
    assert len(merged) == 1
    assert merged[0].chain_id == 2368  # first source wins


@pytest.mark.asyncio
async def test_from_endpoints_drops_blank() -> None:
    """A partial CXR-4 rollout — Base configured but Arbitrum not yet —
    still gives the loop a working multi-chain client. Empty endpoint
    strings vanish from the source list rather than tripping httpx
    on the first request."""
    mc = MultiChainAllocatorGoldsky.from_endpoints(
        {
            2368: "https://example.invalid/kite",
            84_532: "https://example.invalid/base",
            421_614: "",  # blank — should be skipped
        }
    )
    # Three sources requested; two with non-blank endpoints survive.
    # The constructor doesn't HTTP yet — we just inspect the count.
    assert len(mc._sources) == 2  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_from_endpoints_all_blank_falls_back_to_empty_source() -> None:
    """Both endpoints blank should not raise — preserves the offline
    posture so a misconfigured boot returns []."""
    mc = MultiChainAllocatorGoldsky.from_endpoints({2368: "", 84_532: ""})
    assert await mc.fetch_directory() == []


@pytest.mark.asyncio
async def test_multichain_aclose_closes_all_sources() -> None:
    sources: list[Any] = [_FakeSource(2368, []), _FakeSource(84_532, [])]
    mc = MultiChainAllocatorGoldsky(sources=sources)
    await mc.aclose()
    assert all(s.closed for s in sources)
