"""Reference mean_reversion_v1 strategy.

Public, derivative-friendly implementation of the simplest mean-reversion
strategy that satisfies the `mean_reversion_v1.circom` invariants.
Operators clone this directory, swap in their own n-sigma threshold /
lookback / sizing logic, ship to a VPS via `helios deploy`. See
`Helios.md §10.3`.
"""

from mean_reversion_v1.runtime import MeanReversionRuntime, RuntimeConfig
from mean_reversion_v1.strategy import MeanReversionStrategy

__all__ = ["MeanReversionRuntime", "MeanReversionStrategy", "RuntimeConfig"]
__version__ = "0.1.0"
