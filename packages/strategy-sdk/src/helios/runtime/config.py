"""Chain-target + venue-mode resolution.

Resolves `(chain_target, venue_mode)` → `ChainSurface` by reading the
canonical deployment JSON for that chain. Deploy scripts on each
chain write a JSON of identical shape under `contracts/deployments/`:

  {
    "chainId": 84532,
    "lzLocalEid": 40245,
    "addresses": {
      "usdc": "0x...",
      "swapRouter": "0x...",          # canonical UniV3 / Algebra
      "mockSwapRouter": "0x...",      # SDK fallback
      "aavePool": "0x...",            # canonical Aave V3 (arb-sepolia)
      "mockYieldVault": "0x...",      # SDK fallback
      "strategyVaultMomentum": "0x...",
      "strategyVaultYieldRotation": "0x...",
      ...
    }
  }

The SDK does not bundle deployment files. The consumer (a reference
strategy's service module, or a test) passes `deployments_dir=` to
locate them. By default we walk up from `Path.cwd()` looking for
`contracts/deployments/` so a strategy run from a workspace checkout
"just works" without configuration.

phase5-plan.md §WS4.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class ChainTarget(StrEnum):
    """The three v1 chains. Value is the deployment JSON label."""

    KITE_TESTNET = "kite-testnet"
    BASE_SEPOLIA = "base-sepolia"
    ARBITRUM_SEPOLIA = "arbitrum-sepolia"


class VenueMode(StrEnum):
    """Real venue (canonical UniV3 pool / Aave market) vs the mock
    fallback the SDK ships for demo-safety when testnet liquidity
    flakes. Both addresses are recorded in the deployment JSON; the
    fallback is never the default."""

    REAL = "real"
    MOCK = "mock"


class DeploymentNotFoundError(FileNotFoundError):
    """Raised when the expected deployment JSON for a chain target is
    missing. The error message includes the path that was probed so
    the operator can either `forge script Deploy<Chain>.s.sol` or set
    `deployments_dir` explicitly."""


@dataclass(frozen=True, slots=True)
class ChainSurface:
    """Resolved chain-deployment view consumed by executors + the SDK
    web3 client. `venue_address` is whichever of (real, mock) was
    selected by `VenueMode`; both raw addresses are kept on the
    struct so callers that need to reference the alternative (e.g.
    preflight health checks) don't have to re-read the JSON."""

    chain_target: ChainTarget
    chain_id: int
    venue_mode: VenueMode
    rpc_url: str
    """`venue_address` is the address actually called by the strategy
    executor. For momentum it's a swap router; for yield-rotation
    it's a lending pool / vault."""
    venue_address: str
    venue_real: str
    venue_mock: str
    strategy_vault_momentum: str
    strategy_vault_mean_reversion: str
    strategy_vault_yield_rotation: str
    usdc: str
    """LayerZero V2 endpoint id of this chain. Zero if not deployed
    yet (e.g. the canonical Kite JSON predates Phase-5 wiring)."""
    lz_local_eid: int = 0


_KITE_CHAIN_ID = 2368
_BASE_SEPOLIA_CHAIN_ID = 84_532
_ARBITRUM_SEPOLIA_CHAIN_ID = 421_614


_EXPECTED_CHAIN_ID: dict[ChainTarget, int] = {
    ChainTarget.KITE_TESTNET: _KITE_CHAIN_ID,
    ChainTarget.BASE_SEPOLIA: _BASE_SEPOLIA_CHAIN_ID,
    ChainTarget.ARBITRUM_SEPOLIA: _ARBITRUM_SEPOLIA_CHAIN_ID,
}


def _venue_keys(target: ChainTarget) -> tuple[str, str]:
    """Return the (real, mock) JSON address keys for this chain's
    primary venue. Kite reuses the legacy `swapRouter` /
    `mockSwapRouter` keys (mean-reversion is the canonical Kite
    strategy and shares momentum's calldata shape on Algebra). The
    DeployPhase5Execution script writes the same key pair on Base,
    and `aavePool`/`mockYieldVault` on Arbitrum."""
    if target == ChainTarget.ARBITRUM_SEPOLIA:
        return "aavePool", "mockYieldVault"
    return "swapRouter", "mockSwapRouter"


def _default_deployments_dir() -> Path:
    """Walk up from cwd looking for `contracts/deployments/`. This is
    a development-mode convenience — production deploys pass
    `deployments_dir=` explicitly from a service Settings."""
    cur = Path.cwd().resolve()
    for ancestor in (cur, *cur.parents):
        candidate = ancestor / "contracts" / "deployments"
        if candidate.is_dir():
            return candidate
    raise DeploymentNotFoundError(
        "contracts/deployments/ not found walking up from cwd; pass deployments_dir= explicitly"
    )


def load_chain_surface(
    chain_target: ChainTarget,
    *,
    venue_mode: VenueMode = VenueMode.REAL,
    rpc_url: str,
    deployments_dir: Path | str | None = None,
) -> ChainSurface:
    """Read `<deployments_dir>/<chain_target>.json` and return the
    resolved surface. Raises `DeploymentNotFoundError` if the JSON
    is missing.

    `rpc_url` is required because the deployment JSON does not carry
    one — RPCs are operator-controlled and live in env."""
    base = _default_deployments_dir() if deployments_dir is None else Path(deployments_dir)
    path = base / f"{chain_target.value}.json"
    if not path.is_file():
        raise DeploymentNotFoundError(f"deployment JSON not found: {path}")
    raw = json.loads(path.read_text())

    chain_id = int(raw.get("chainId", 0))
    expected = _EXPECTED_CHAIN_ID[chain_target]
    if chain_id != expected:
        raise ValueError(f"chainId mismatch in {path}: file claims {chain_id}, expected {expected}")

    addresses = raw.get("addresses", {})
    real_key, mock_key = _venue_keys(chain_target)
    venue_real = str(addresses.get(real_key, ""))
    venue_mock = str(addresses.get(mock_key, ""))
    selected = venue_real if venue_mode == VenueMode.REAL else venue_mock
    if not selected:
        raise ValueError(
            f"venue address missing in {path} (mode={venue_mode.value}, key="
            f"{real_key if venue_mode == VenueMode.REAL else mock_key})"
        )

    return ChainSurface(
        chain_target=chain_target,
        chain_id=chain_id,
        venue_mode=venue_mode,
        rpc_url=rpc_url,
        venue_address=selected,
        venue_real=venue_real,
        venue_mock=venue_mock,
        strategy_vault_momentum=str(addresses.get("strategyVaultMomentum", "")),
        strategy_vault_mean_reversion=str(addresses.get("strategyVaultMeanReversion", "")),
        strategy_vault_yield_rotation=str(addresses.get("strategyVaultYieldRotation", "")),
        usdc=str(addresses.get("usdc", "")),
        lz_local_eid=int(raw.get("lzLocalEid", 0)),
    )
