"""Public types exposed to yield-rotation strategy operators.

WS4: lifted into the SDK at `helios.types`. This module re-exports the
canonical SDK types so existing imports (`from yield_rotation_v1.types
import YieldTick, RotationIntent`) keep working — third-party strategy
authors are encouraged to import from `helios` directly going forward.

`yield_rotation_v1` is structurally distinct from the directional
strategy classes — there's no asset-pair swap, no slippage, no per-bar
price observations. The strategy fires on *yield* updates: an APY
differential between two allowlisted lending markets.
"""

from __future__ import annotations

from helios.types import RotationIntent, YieldTick

__all__ = ["RotationIntent", "YieldTick"]
