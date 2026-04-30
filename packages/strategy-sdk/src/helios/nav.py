"""NAV / drawdown / Sharpe helpers used by the backtest engine and any
SDK-side observability surface.

Pure-Python on purpose: no numpy/pandas dependency for an SDK that
should `pip install` cleanly into bare environments. Math matches the
formulas the reputation engine consumes (`Helios.md §8.2`), so SDK
backtests and the cohort scoring loop see the same series shape.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# Bars per year for annualisation. The SDK speaks 1-minute bars by
# default (`MarketSnapshot.bar_interval_sec = 60`); 525_600 minutes/year
# matches the convention used by `services/reputation/windows.py`.
BARS_PER_YEAR_1M = 525_600


@dataclass
class NAVTracker:
    """Append-only NAV time series with online drawdown + Sharpe.

    All values are USD floats. The tracker stores both the raw NAV
    series (for drawdown) and per-bar simple returns (for Sharpe);
    both are O(1) per `record(...)` call."""

    initial_nav: float
    bars_per_year: int = BARS_PER_YEAR_1M
    _navs: list[float] = field(default_factory=list)
    _returns: list[float] = field(default_factory=list)
    _peak: float = 0.0
    _max_drawdown: float = 0.0

    def __post_init__(self) -> None:
        if self.initial_nav <= 0:
            raise ValueError("initial_nav must be > 0")
        self._navs.append(float(self.initial_nav))
        self._peak = float(self.initial_nav)

    def record(self, nav: float) -> None:
        nav = float(nav)
        prev = self._navs[-1]
        self._navs.append(nav)
        if prev > 0:
            self._returns.append((nav - prev) / prev)
        else:
            self._returns.append(0.0)
        self._peak = max(self._peak, nav)
        if self._peak > 0:
            dd = (self._peak - nav) / self._peak
            self._max_drawdown = max(self._max_drawdown, dd)

    @property
    def navs(self) -> list[float]:
        return list(self._navs)

    @property
    def returns(self) -> list[float]:
        return list(self._returns)

    @property
    def current(self) -> float:
        return self._navs[-1]

    @property
    def peak(self) -> float:
        return self._peak

    @property
    def max_drawdown(self) -> float:
        """Maximum peak-to-trough drawdown observed, as a fraction in [0, 1]."""
        return self._max_drawdown

    @property
    def total_return(self) -> float:
        first = self._navs[0]
        if first <= 0:
            return 0.0
        return (self._navs[-1] - first) / first

    def sharpe(self, risk_free_rate_per_bar: float = 0.0) -> float:
        """Annualised Sharpe of the per-bar simple returns.

        Returns 0.0 when fewer than 2 returns or zero stdev — keeps the
        backtest report numerically clean rather than NaN-poisoned."""
        excess = [r - risk_free_rate_per_bar for r in self._returns]
        n = len(excess)
        if n < 2:
            return 0.0
        mean = sum(excess) / n
        var = sum((x - mean) ** 2 for x in excess) / (n - 1)
        sd = math.sqrt(var)
        if sd == 0:
            return 0.0
        return (mean / sd) * math.sqrt(self.bars_per_year)


def max_drawdown(navs: list[float]) -> float:
    """Standalone max-drawdown over a NAV series (e.g. for ad-hoc analysis)."""
    if not navs:
        return 0.0
    peak = navs[0]
    worst = 0.0
    for n in navs:
        peak = max(peak, n)
        if peak > 0:
            dd = (peak - n) / peak
            worst = max(worst, dd)
    return worst


def sharpe_ratio(returns: list[float], bars_per_year: int = BARS_PER_YEAR_1M) -> float:
    """Annualised Sharpe over a list of per-bar simple returns."""
    n = len(returns)
    if n < 2:
        return 0.0
    mean = sum(returns) / n
    var = sum((x - mean) ** 2 for x in returns) / (n - 1)
    sd = math.sqrt(var)
    if sd == 0:
        return 0.0
    return (mean / sd) * math.sqrt(bars_per_year)
