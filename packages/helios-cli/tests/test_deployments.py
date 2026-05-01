"""`_deployments` — read addresses from contracts/deployments/<chain>.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from helios_cli import _deployments


def test_load_uses_env_override(deployments_dir: Path) -> None:
    d = _deployments.load("kite-testnet")
    assert d.chain_id == 2368
    assert d.addresses["usdc"].startswith("0x")


def test_require_missing_key(deployments_dir: Path) -> None:
    d = _deployments.load("kite-testnet")
    with pytest.raises(_deployments.DeploymentsError, match="missing `nonExistent`"):
        d.require("nonExistent")


def test_unknown_chain(deployments_dir: Path) -> None:
    with pytest.raises(_deployments.DeploymentsError, match="no deployment file"):
        _deployments.load("base-sepolia")


def test_malformed_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "contracts" / "deployments"
    root.mkdir(parents=True)
    (root / "kite-testnet.json").write_text("{not json")
    monkeypatch.setenv("HELIOS_DEPLOYMENTS_DIR", str(root))
    with pytest.raises(_deployments.DeploymentsError, match="not valid JSON"):
        _deployments.load("kite-testnet")


def test_chainid_falls_back_to_known_chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "contracts" / "deployments"
    root.mkdir(parents=True)
    (root / "anvil.json").write_text(json.dumps({"addresses": {}}))
    monkeypatch.setenv("HELIOS_DEPLOYMENTS_DIR", str(root))
    d = _deployments.load("anvil")
    assert d.chain_id == 31_337
