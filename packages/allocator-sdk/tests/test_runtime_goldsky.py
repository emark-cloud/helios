"""Smoke tests for `AllocatorGoldsky` directory parsing.

Live HTTP integration runs in the Phase 3 e2e (`scripts/e2e-phase3.sh`).
Here we only need: the offline-tolerant path returns []; the parse
+ candidate-mapping logic produces the expected shape.
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
