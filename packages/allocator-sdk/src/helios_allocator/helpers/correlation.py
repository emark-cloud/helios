"""Pairwise correlation + Helix correlation-aware greedy pick.

Spec: `Helios.md §11.4.1 (b)`.

Correlation is computed over log-returns of the NAV series, not raw
NAV — raw NAV correlation is dominated by long-run drift (everything
that goes up trends together; the question is whether they wiggle
together).

v1 Helix-lite does not call `helix_greedy_pick` (the v1 callout pins
correlation-aware allocation to v2). The helper ships and is tested so
third-party allocators can wire it earlier than Helix does.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol

from helios_allocator.helpers._math import log_returns, pearson_correlation
from helios_allocator.types import MetaStrategy, StrategyCandidate


class _NavHistoryReader(Protocol):
    """Subset of `AllocatorGoldsky` (or any custom data source) needed
    by `pairwise_correlation_from_goldsky`."""

    async def fetch_nav_history(self, strategy_id: str, *, window_days: int) -> list[float]: ...


def pairwise_correlation(
    nav_series_a: Sequence[float],
    nav_series_b: Sequence[float],
) -> float:
    """Pearson correlation of log-returns over two NAV traces.

    Returns 0.0 when either series is too short to produce returns.
    Series of differing lengths are aligned to the shorter return tail
    (assumes both end at the same observation, which is what
    Goldsky-sourced rolling windows produce).
    """
    if len(nav_series_a) < 2 or len(nav_series_b) < 2:
        return 0.0
    ra = log_returns(nav_series_a)
    rb = log_returns(nav_series_b)
    n = min(len(ra), len(rb))
    if n < 2:
        return 0.0
    return pearson_correlation(ra[-n:], rb[-n:])


async def pairwise_correlation_from_goldsky(
    goldsky: _NavHistoryReader,
    strategy_a: str,
    strategy_b: str,
    *,
    window_days: int = 30,
) -> float:
    """Fetch 30-day NAV traces for both strategies and compute log-return
    Pearson correlation. Returns 0.0 if either series is unavailable."""
    nav_a = await goldsky.fetch_nav_history(strategy_a, window_days=window_days)
    nav_b = await goldsky.fetch_nav_history(strategy_b, window_days=window_days)
    return pairwise_correlation(nav_a, nav_b)


CorrelationFn = Callable[[str, str], Awaitable[float]]


async def helix_greedy_pick(
    user: MetaStrategy,
    ranked: Sequence[StrategyCandidate],
    *,
    get_correlation: CorrelationFn,
    max_pairwise_correlation: float = 0.7,
) -> list[StrategyCandidate]:
    """Greedy selection: iterate `ranked` in score order, skip any
    candidate whose average pairwise correlation with the
    already-selected portfolio exceeds `max_pairwise_correlation`.

    `get_correlation(a, b)` is injected so the picker stays decoupled
    from any specific NAV-history source — pass
    `lambda a, b: pairwise_correlation_from_goldsky(goldsky, a, b)`
    for the production wiring.
    """
    selected: list[StrategyCandidate] = []
    for candidate in ranked:
        if len(selected) >= user.max_strategies_count:
            break
        if not selected:
            avg_corr = 0.0
        else:
            corrs = [await get_correlation(candidate.strategy_id, s.strategy_id) for s in selected]
            avg_corr = sum(corrs) / len(corrs)
        if avg_corr <= max_pairwise_correlation:
            selected.append(candidate)
    return selected
