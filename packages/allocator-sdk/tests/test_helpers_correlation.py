"""WS1.B helpers: pairwise correlation + Helix correlation-aware greedy pick."""

from __future__ import annotations

import math

import pytest
from helios_allocator.helpers import (
    helix_greedy_pick,
    pairwise_correlation,
    pairwise_correlation_from_goldsky,
)
from helios_allocator.types import MetaStrategy, StrategyCandidate


def _meta(*, max_strategies_count: int = 3) -> MetaStrategy:
    return MetaStrategy(
        user_address="0x" + "ab" * 20,
        allowed_strategy_classes=("momentum_v1",),
        allowed_assets=("USDC",),
        allowed_chains=(2368,),
        max_capital_usd=10_000,
        max_per_strategy_bps=5_000,
        max_strategies_count=max_strategies_count,
        drawdown_threshold_bps=1_500,
        max_fee_rate_bps=2_500,
        rebalance_cadence_sec=900,
        valid_until=2_000_000_000,
    )


def _candidate(sid_byte: str) -> StrategyCandidate:
    return StrategyCandidate(
        strategy_id="0x" + sid_byte * 20,
        declared_class="momentum_v1",
        chain_id=2368,
        operator="0x" + "cc" * 20,
        fee_rate_bps=1_000,
        stake_amount_usd=5_000,
        max_capacity_usd=100_000,
        current_allocations_usd=0,
        reputation_score=0.8,
    )


# ── pairwise_correlation ──────────────────────────────────────


def test_pairwise_correlation_perfect_positive() -> None:
    """Identical NAV traces → log-returns identical → ρ = 1.0."""
    nav = [100.0, 110.0, 105.0, 120.0, 130.0, 125.0]
    assert pairwise_correlation(nav, nav) == pytest.approx(1.0)


def test_pairwise_correlation_perfect_negative() -> None:
    """Mirror-image log-returns → ρ = -1.0.

    Construct B's NAV so each step's log-return is the negation of A's.
    """
    nav_a = [100.0, 110.0, 105.0, 120.0]
    returns_a = [math.log(nav_a[i] / nav_a[i - 1]) for i in range(1, len(nav_a))]
    nav_b = [100.0]
    for r in returns_a:
        nav_b.append(nav_b[-1] * math.exp(-r))
    assert pairwise_correlation(nav_a, nav_b) == pytest.approx(-1.0)


def test_pairwise_correlation_zero_for_orthogonal_series() -> None:
    """Returns that sum to zero with mirrored sign pattern: should be
    near-zero correlation (not exactly zero due to discrete alignment)."""
    nav_a = [100.0, 110.0, 100.0, 110.0, 100.0]  # alternating up/down
    nav_b = [100.0, 100.0, 110.0, 110.0, 100.0]  # phase-shifted
    rho = pairwise_correlation(nav_a, nav_b)
    assert abs(rho) < 0.6  # not perfectly zero, but clearly not collinear


def test_pairwise_correlation_returns_zero_for_short_series() -> None:
    assert pairwise_correlation([100.0], [100.0]) == 0.0
    assert pairwise_correlation([], []) == 0.0


def test_pairwise_correlation_aligns_to_shorter_tail() -> None:
    """Series of unequal length: align to the shorter return tail.
    Otherwise mismatched lengths would crash the Pearson reduction."""
    nav_long = [100.0, 110.0, 105.0, 120.0, 115.0, 130.0]
    nav_short = [100.0, 95.0, 105.0]
    rho = pairwise_correlation(nav_long, nav_short)
    assert -1.0 <= rho <= 1.0  # finite, no crash


def test_pairwise_correlation_uses_log_returns_not_raw_nav() -> None:
    """Two NAV series that drift up together but oscillate independently
    should have *log-return* correlation near 0. Raw NAV correlation
    over the same period is dominated by the shared trend and looks
    near 1 — confirming we're computing on returns, not levels.
    """
    nav_a = [100.0, 102.0, 101.0, 104.0, 103.0, 106.0]  # up trend, jitter +/-
    nav_b = [100.0, 99.0, 102.0, 101.0, 105.0, 104.0]  # up trend, opposite jitter
    rho = pairwise_correlation(nav_a, nav_b)
    assert rho < 0.5  # log-return correlation is modest at most


# ── pairwise_correlation_from_goldsky ─────────────────────────


class _StubGoldsky:
    def __init__(self, histories: dict[str, list[float]]) -> None:
        self._histories = histories

    async def fetch_nav_history(self, strategy_id: str, *, window_days: int) -> list[float]:
        return list(self._histories.get(strategy_id, []))[-window_days:]


@pytest.mark.asyncio
async def test_pairwise_correlation_from_goldsky_delegates_correctly() -> None:
    sa = "0x" + "11" * 20
    sb = "0x" + "22" * 20
    nav_a = [100.0, 110.0, 105.0, 120.0]
    goldsky = _StubGoldsky({sa: nav_a, sb: nav_a})  # identical → ρ=1
    rho = await pairwise_correlation_from_goldsky(goldsky, sa, sb, window_days=30)
    assert rho == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_pairwise_correlation_from_goldsky_zero_when_history_missing() -> None:
    sa = "0x" + "11" * 20
    sb = "0x" + "22" * 20
    goldsky = _StubGoldsky({sa: [100.0, 110.0, 120.0]})  # b missing
    rho = await pairwise_correlation_from_goldsky(goldsky, sa, sb)
    assert rho == 0.0


# ── helix_greedy_pick ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_helix_greedy_pick_includes_first_candidate_unconditionally() -> None:
    user = _meta(max_strategies_count=2)
    a = _candidate("11")
    b = _candidate("22")

    # Both perfectly correlated; picker still takes A (no portfolio yet).
    async def corr(_x: str, _y: str) -> float:
        return 1.0

    selected = await helix_greedy_pick(
        user, [a, b], get_correlation=corr, max_pairwise_correlation=0.7
    )
    assert [s.strategy_id for s in selected] == [a.strategy_id]


@pytest.mark.asyncio
async def test_helix_greedy_pick_skips_correlated_candidate_picks_next() -> None:
    """Spec example from `Helios.md §11.4.1 (b)`:
    rank order [A, B, C], corr(A, B)=0.9, corr(A, C)=0.3, threshold 0.7
    → selects [A, C] not [A, B].
    """
    user = _meta(max_strategies_count=2)
    a = _candidate("11")
    b = _candidate("22")
    c = _candidate("33")

    async def corr(x: str, y: str) -> float:
        pair = frozenset({x, y})
        if pair == frozenset({a.strategy_id, b.strategy_id}):
            return 0.9
        if pair == frozenset({a.strategy_id, c.strategy_id}):
            return 0.3
        return 0.0

    selected = await helix_greedy_pick(
        user, [a, b, c], get_correlation=corr, max_pairwise_correlation=0.7
    )
    assert [s.strategy_id for s in selected] == [a.strategy_id, c.strategy_id]


@pytest.mark.asyncio
async def test_helix_greedy_pick_respects_max_strategies_count() -> None:
    user = _meta(max_strategies_count=2)
    a = _candidate("11")
    b = _candidate("22")
    c = _candidate("33")

    async def corr(_x: str, _y: str) -> float:
        return 0.0  # all uncorrelated

    selected = await helix_greedy_pick(
        user, [a, b, c], get_correlation=corr, max_pairwise_correlation=0.7
    )
    assert len(selected) == 2
    assert [s.strategy_id for s in selected] == [a.strategy_id, b.strategy_id]


@pytest.mark.asyncio
async def test_helix_greedy_pick_empty_input_returns_empty() -> None:
    user = _meta()

    async def corr(_x: str, _y: str) -> float:
        return 0.0

    selected = await helix_greedy_pick(user, [], get_correlation=corr)
    assert selected == []
