"""Per-class cohort statistics for `NormalizedSharpe` (`Helios.md §8.2`).

For each class and each window (7d/30d/90d), the engine collects every active
strategy's window Sharpe and computes the cohort median + IQR. A given
strategy's normalized Sharpe is `(Sharpe - median) / IQR`. When the cohort is
too thin to define those statistics meaningfully, this module returns the
explicit raw-Sharpe fallback documented in `Helios.md §8.7`: median = 0,
IQR = 1, so `normalize(s, ...)` collapses to `(s - 0) / 1 = s`. This is the
cold-start path — a fresh class with fewer than `MIN_COHORT_SIZE` active
strategies cannot have meaningful cross-strategy ranking, so each strategy
is judged against the absolute zero baseline until the cohort fills out.

WS7.B sets `MIN_COHORT_SIZE = 3` (was 2 in the WS2.A draft) so the median +
range proxy used for n=2/3 is never computed against a single peer.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass

MIN_COHORT_SIZE = 3


@dataclass(frozen=True, slots=True)
class CohortStats:
    size: int
    median: float
    iqr: float
    is_fallback: bool


_NEUTRAL = CohortStats(size=0, median=0.0, iqr=1.0, is_fallback=True)


def cohort_stats(sharpes: Sequence[float]) -> CohortStats:
    n = len(sharpes)
    if n < MIN_COHORT_SIZE:
        return CohortStats(size=n, median=0.0, iqr=1.0, is_fallback=True)
    sorted_s = sorted(sharpes)
    median = statistics.median(sorted_s)
    if n >= 4:
        q1, _, q3 = statistics.quantiles(sorted_s, n=4, method="exclusive")
        iqr = q3 - q1
    else:
        # 2 or 3 strategies: classical IQR is undefined / degenerate. Use the
        # full range as a robust spread proxy so cohorts of 2-3 still produce
        # a usable normalized Sharpe.
        iqr = sorted_s[-1] - sorted_s[0]
    if iqr <= 0:
        # All strategies tied (or single-value cohort): no spread → neutral.
        return CohortStats(size=n, median=median, iqr=1.0, is_fallback=True)
    return CohortStats(size=n, median=median, iqr=iqr, is_fallback=False)


def normalize(sharpe: float, stats: CohortStats) -> float:
    return (sharpe - stats.median) / stats.iqr


def neutral() -> CohortStats:
    return _NEUTRAL
