"""Chain-aware runtime helpers.

Phase-5 added cross-chain execution: a single strategy class can run
on Kite (Algebra venue), Base Sepolia (real Uniswap V3), or Arbitrum
Sepolia (real Aave V3). The SDK resolves chain-specific addresses at
runtime from the canonical `contracts/deployments/<label>.json`
artifacts written by the deploy scripts.

Public surface:
  * `ChainTarget` — enum of the three supported chains.
  * `VenueMode` — `REAL` (canonical pool/market) vs `MOCK` (the
    fallback router/yield vault deployed alongside for demo safety).
  * `ChainSurface` — resolved view of one deployment: rpc, chain id,
    strategy vault address, venue contract.
  * `load_chain_surface(...)` — reads a deployment JSON by chain
    target, applies env overrides, returns a `ChainSurface`.

This subpackage has **no** runtime workspace dependencies. The wheel
installs from public PyPI; tests stub the deployment dir via the
`deployments_dir` argument.
"""

from helios.runtime.config import (
    ChainSurface,
    ChainTarget,
    DeploymentNotFoundError,
    VenueMode,
    load_chain_surface,
)

__all__ = [
    "ChainSurface",
    "ChainTarget",
    "DeploymentNotFoundError",
    "VenueMode",
    "load_chain_surface",
]
