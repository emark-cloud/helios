"""Position-sizing helpers (WS4 PR 3/3).

The default sizing path inside `StrategyAgent.size_trade` clamps every
intent to `available_capital` — free cash. That's correct on day zero
but reads the wrong base on a half-deployed strategy: a momentum agent
that holds a long position has its free cash already half-used, and
re-applying `position_fraction × available_capital` shrinks the next
entry to a quarter of the original target. Run that for 100 bars and
you've leveraged yourself out of the market without realising it.

`nav_target_notional` reads against mark-to-market NAV instead. It's
the intended sizing rule for any strategy that thinks in terms of
"target X% of NAV per trade." Strategies opt in two ways:

  1. Compute their desired notional via `nav_target_notional(self,
     fraction)` and stuff the result into `TradeIntent.amount_in_usd`.
  2. Set `TradeIntent.is_nav_targeted=True` so the engine's
     `size_trade(... , nav_target=True)` path lets the notional clear
     `available_capital` (clamped at NAV instead). The engine still
     down-sizes if free cash literally cannot cover the entry, so a
     fully-deployed strategy never overdrafts.

The reference momentum and mean-reversion strategies adopted this
flow in WS4; the YR scaffold uses the helper for its rotation
amount.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from helios.agent import StrategyAgent


def nav_target_notional(
    strategy: StrategyAgent,
    fraction: float,
    *,
    max_position_size_usd: int | None = None,
) -> float:
    """Compute a NAV-fraction target notional that does not shrink as
    the strategy deploys capital.

    Returns `min(strategy.nav * fraction, max_position_size_usd)`.
    Falls back to the strategy's class-level `max_position_size_usd`
    if no override is supplied. Always non-negative.
    """
    if fraction <= 0:
        return 0.0
    cap_int = (
        max_position_size_usd
        if max_position_size_usd is not None
        else strategy.max_position_size_usd
    )
    cap = float(cap_int) if cap_int else float("inf")
    desired = max(0.0, strategy.nav * fraction)
    return min(desired, cap)


__all__ = ["nav_target_notional"]
