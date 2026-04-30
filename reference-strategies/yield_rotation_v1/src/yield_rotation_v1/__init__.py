"""Reference yield_rotation_v1 strategy.

Public, derivative-friendly implementation of the simplest yield-rotation
strategy that satisfies the `yield_rotation_v1.circom` invariants.
Operators clone this directory, swap in their own threshold / bridging
cost / market universe, ship to a VPS via `helios deploy`. See
`Helios.md §10.4`.
"""

from yield_rotation_v1.runtime import RuntimeConfig, YieldRotationRuntime
from yield_rotation_v1.strategy import YieldRotationStrategy
from yield_rotation_v1.types import RotationIntent, YieldTick

__all__ = [
    "RotationIntent",
    "RuntimeConfig",
    "YieldRotationRuntime",
    "YieldRotationStrategy",
    "YieldTick",
]
__version__ = "0.1.0"
