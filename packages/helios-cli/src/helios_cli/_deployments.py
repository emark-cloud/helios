"""Read deployed contract addresses from `contracts/deployments/<chain>.json`.

The Foundry deploy scripts write a single JSON per chain; the CLI reads
that file directly so a redeploy doesn't require regenerating any
Python module. Resolution order for the deployments root:

  1. `HELIOS_DEPLOYMENTS_DIR` env var (test override)
  2. walk up from CWD until we hit a `contracts/deployments/` dir
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CHAIN = "kite-testnet"
CHAIN_IDS: dict[str, int] = {
    "kite-testnet": 2368,
    "anvil": 31_337,
    "base-sepolia": 84_532,
    "arbitrum-sepolia": 421_614,
}


class DeploymentsError(RuntimeError):
    """Raised when the deployments file is missing or malformed."""


@dataclass(frozen=True, slots=True)
class Deployment:
    chain: str
    chain_id: int
    addresses: dict[str, str]

    def require(self, key: str) -> str:
        addr = self.addresses.get(key)
        if not addr:
            raise DeploymentsError(
                f"deployments/{self.chain}.json is missing `{key}` — "
                "redeploy or pass the address explicitly."
            )
        return addr


def deployments_root() -> Path:
    override = os.environ.get("HELIOS_DEPLOYMENTS_DIR")
    if override:
        path = Path(override)
        if not path.exists():
            raise DeploymentsError(f"HELIOS_DEPLOYMENTS_DIR={override} does not exist")
        return path
    here = Path.cwd().resolve()
    for ancestor in (here, *here.parents):
        candidate = ancestor / "contracts" / "deployments"
        if candidate.is_dir():
            return candidate
    raise DeploymentsError(
        "could not locate contracts/deployments — run from inside a Helios "
        "checkout or set HELIOS_DEPLOYMENTS_DIR."
    )


def load(chain: str = DEFAULT_CHAIN) -> Deployment:
    root = deployments_root()
    path = root / f"{chain}.json"
    if not path.exists():
        raise DeploymentsError(f"no deployment file at {path}")
    try:
        body = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise DeploymentsError(f"{path} is not valid JSON: {exc}") from exc
    addresses = body.get("addresses") or {}
    chain_id = int(body.get("chainId") or CHAIN_IDS.get(chain, 0))
    if chain_id == 0:
        raise DeploymentsError(f"{path} has no chainId and chain `{chain}` is unknown")
    return Deployment(chain=chain, chain_id=chain_id, addresses=addresses)


__all__ = ["CHAIN_IDS", "DEFAULT_CHAIN", "Deployment", "DeploymentsError", "load"]
