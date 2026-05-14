"""Reference LLM-driven momentum_v1 strategy.

`LLMMomentumStrategy` subclasses `StrategyAgent` with `declared_class =
"momentum_v1"`, so it reuses the existing momentum_v1 Groth16 verifier,
witness builder, prover, and registry slot. Only the signal source
changes: an Anthropic API call replaces the deterministic threshold
check. The on-chain `params_hash` enforces the operator's declared
bounds — the LLM cannot escape them.

Built to demonstrate end-to-end integration of model-driven agents with
the Helios protocol. See `Helios.md §10.2` and the package README.
"""

from llm_momentum_v1.runtime import LLMMomentumRuntime, RuntimeConfig
from llm_momentum_v1.strategy import DEFAULT_SYSTEM_PROMPT, LLMMomentumStrategy

__all__ = [
    "DEFAULT_SYSTEM_PROMPT",
    "LLMMomentumRuntime",
    "LLMMomentumStrategy",
    "RuntimeConfig",
]
__version__ = "0.1.0"
