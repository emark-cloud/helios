"""Reference momentum_v1 strategy.

Public, derivative-friendly implementation of the simplest momentum
strategy that satisfies the `momentum_v1.circom` invariants. Operators
clone this directory, swap in their own threshold / lookback / sizing
logic, ship to a VPS via `helios deploy`. See `Helios.md §10.2`.
"""

from momentum_v1.runtime import MomentumRuntime, RuntimeConfig
from momentum_v1.strategy import MomentumStrategy

__all__ = ["MomentumRuntime", "MomentumStrategy", "RuntimeConfig"]
__version__ = "0.1.0"
