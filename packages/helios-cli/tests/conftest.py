"""Shared fixtures for helios-cli tests."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest


@pytest.fixture
def tiny_strategy_file(tmp_path: Path) -> Path:
    """A 5-line StrategyAgent that always returns None — exercises the
    backtest engine end-to-end without taking any positions, so report
    shape is deterministic regardless of price walk."""
    body = textwrap.dedent(
        """
        from helios import StrategyAgent

        class NoopStrategy(StrategyAgent):
            declared_class = "test_class_v1"
            asset_universe = ("USDC", "BTC", "ETH")
            max_position_size_usd = 1_000
            fee_rate_bps = 0

            def on_bar(self, asset, snapshot):
                return None
        """
    )
    path = tmp_path / "noop.py"
    path.write_text(body)
    return path


@pytest.fixture
def deployments_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Stand up a temp `contracts/deployments` tree so the CLI's
    deployments helper has something to read without depending on the
    repo's actual deployments file (which Track-A bootstrap may not have
    populated)."""
    root = tmp_path / "contracts" / "deployments"
    root.mkdir(parents=True)
    (root / "kite-testnet.json").write_text(
        json.dumps(
            {
                "chainId": 2368,
                "addresses": {
                    "usdc": "0xe8cf8a5711f08d5211d46a2835ecc9c9af1b91cd",
                    "strategyRegistry": "0x3a0f5b9436eca0c8c0eced659dcc41e86e65e33d",
                    "tradeAttestationVerifier": "0x743e1bd7e9795e78b10965eaeaa93bf215476c96",
                },
            }
        )
    )
    monkeypatch.setenv("HELIOS_DEPLOYMENTS_DIR", str(root))
    return root
