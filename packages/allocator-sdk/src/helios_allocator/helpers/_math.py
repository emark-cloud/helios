"""Pure math primitives shared across helpers.

Kept private (`_math`) so allocator authors consume the named entry
points (`detect_regime`, `pairwise_correlation`, `realized_volatility`,
...) rather than the underlying reductions. Stable API surface =
the stuff exported from `helpers/__init__.py`.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def log_returns(prices: Sequence[float]) -> list[float]:
    """Continuous compounded returns: ln(P_t / P_{t-1}). Drops the first
    observation. Raises on non-positive prices — log of a non-positive
    is undefined and silently swallowing that produces a vol estimate
    that's wrong by orders of magnitude.
    """
    out: list[float] = []
    prev: float | None = None
    for p in prices:
        if p <= 0:
            raise ValueError("price series must be strictly positive")
        if prev is not None:
            out.append(math.log(p / prev))
        prev = p
    return out


def realized_volatility(returns: Sequence[float], periods_per_year: int = 365) -> float:
    """Annualized sample standard deviation of returns.

    Defaults to 365 (calendar-day) annualization rather than 252
    (trading-day) because crypto runs continuously. Helios.md §11.4.1
    doesn't pin this — the regime band p20/p80 is invariant to the
    choice as long as the same annualization is used everywhere.
    Returns 0.0 for fewer than two observations.
    """
    n = len(returns)
    if n < 2:
        return 0.0
    mean = sum(returns) / n
    variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
    return math.sqrt(variance) * math.sqrt(periods_per_year)


def percentile(sorted_values: Sequence[float], level: float) -> float:
    """Linear-interpolation percentile (numpy default `linear` method).
    Caller is responsible for sorting."""
    if not sorted_values:
        raise ValueError("cannot take percentile of empty sequence")
    if not 0.0 <= level <= 1.0:
        raise ValueError("level must be in [0, 1]")
    n = len(sorted_values)
    if n == 1:
        return float(sorted_values[0])
    pos = level * (n - 1)
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return float(sorted_values[lo]) * (1.0 - frac) + float(sorted_values[hi]) * frac


def percentiles(values: Sequence[float], levels: Sequence[float]) -> dict[str, float]:
    """Returns `{f"p{int(level*100)}": value}` for each requested level."""
    sorted_vals = sorted(float(v) for v in values)
    return {f"p{round(level * 100)}": percentile(sorted_vals, level) for level in levels}


def pearson_correlation(xs: Sequence[float], ys: Sequence[float]) -> float:
    """Pearson correlation coefficient. Returns 0.0 for series of length
    < 2 or when either series has zero variance (an all-flat series is
    uncorrelated with anything by convention).
    """
    n = len(xs)
    if n != len(ys):
        raise ValueError("series must have equal length")
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0.0 or syy == 0.0:
        return 0.0
    return num / math.sqrt(sxx * syy)
