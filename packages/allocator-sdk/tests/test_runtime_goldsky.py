"""Smoke tests for `AllocatorGoldsky` directory parsing.

Live HTTP integration runs against the live Goldsky endpoint via the
deployed allocator services. Here we only need: the offline-tolerant
path returns []; the parse + candidate-mapping logic produces the
expected shape.
"""

from __future__ import annotations

import pytest
from helios_allocator.runtime.goldsky import (
    AllocatorGoldsky,
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
