"""WS4 — chain-target / venue-mode resolution.

Builds a synthetic deployment dir under tmp_path and confirms
`load_chain_surface` selects the right venue address per
`(chain_target, venue_mode)`. No real RPCs touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from helios.runtime import (
    ChainSurface,
    ChainTarget,
    DeploymentNotFoundError,
    VenueMode,
    load_chain_surface,
)


def _write_deployments(tmp_path: Path) -> Path:
    base = tmp_path / "deployments"
    base.mkdir()

    (base / "kite-testnet.json").write_text(
        json.dumps(
            {
                "chainId": 2368,
                "addresses": {
                    "usdc": "0xe8cf8a5711f08d5211d46a2835ecc9c9af1b91cd",
                    "swapRouter": "0x55782e7019f4619a06a25bf66d2998c8fe2cc436",
                    "mockSwapRouter": "0x55782e7019f4619a06a25bf66d2998c8fe2cc436",
                    "strategyVaultMomentum": "0xf11d55a3057a3da51c9ed63bdc6ae8f666fa426a",
                    "strategyVaultMeanReversion": "0xe85fc70edc752d3ff283f3fffa17598d32b5fc07",
                    "strategyVaultYieldRotation": "0xb7496be712ed62fb02c6b9665f74ee6ff136d0d7",
                },
            }
        )
    )

    (base / "base-sepolia.json").write_text(
        json.dumps(
            {
                "chainId": 84_532,
                "lzLocalEid": 40_245,
                "addresses": {
                    "usdc": "0x1111111111111111111111111111111111111111",
                    "swapRouter": "0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4",
                    "mockSwapRouter": "0x2222222222222222222222222222222222222222",
                    "strategyVaultMomentum": "0x3333333333333333333333333333333333333333",
                    "strategyVaultMeanReversion": "0x0000000000000000000000000000000000000000",
                    "strategyVaultYieldRotation": "0x0000000000000000000000000000000000000000",
                },
            }
        )
    )

    (base / "arbitrum-sepolia.json").write_text(
        json.dumps(
            {
                "chainId": 421_614,
                "lzLocalEid": 40_231,
                "addresses": {
                    "usdc": "0x4444444444444444444444444444444444444444",
                    "aavePool": "0xBfC91D59fdAA134A4ED45f7B584cAf96D7792Eff",
                    "mockYieldVault": "0x5555555555555555555555555555555555555555",
                    "strategyVaultYieldRotation": "0x6666666666666666666666666666666666666666",
                    "strategyVaultMomentum": "0x0000000000000000000000000000000000000000",
                    "strategyVaultMeanReversion": "0x0000000000000000000000000000000000000000",
                },
            }
        )
    )
    return base


def test_load_chain_surface_real_uniswap(tmp_path: Path) -> None:
    base = _write_deployments(tmp_path)
    surface = load_chain_surface(
        ChainTarget.BASE_SEPOLIA,
        venue_mode=VenueMode.REAL,
        rpc_url="https://base-sepolia.example",
        deployments_dir=base,
    )
    assert isinstance(surface, ChainSurface)
    assert surface.chain_id == 84_532
    assert surface.venue_mode == VenueMode.REAL
    assert surface.venue_address == "0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4"
    assert surface.venue_real == "0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4"
    assert surface.venue_mock == "0x2222222222222222222222222222222222222222"
    assert surface.lz_local_eid == 40_245
    assert surface.strategy_vault_momentum == "0x3333333333333333333333333333333333333333"


def test_load_chain_surface_mock_fallback(tmp_path: Path) -> None:
    base = _write_deployments(tmp_path)
    surface = load_chain_surface(
        ChainTarget.BASE_SEPOLIA,
        venue_mode=VenueMode.MOCK,
        rpc_url="https://base-sepolia.example",
        deployments_dir=base,
    )
    assert surface.venue_address == "0x2222222222222222222222222222222222222222"
    assert surface.venue_mode == VenueMode.MOCK


def test_load_chain_surface_arbitrum_uses_aave_keys(tmp_path: Path) -> None:
    base = _write_deployments(tmp_path)
    surface = load_chain_surface(
        ChainTarget.ARBITRUM_SEPOLIA,
        venue_mode=VenueMode.REAL,
        rpc_url="https://arb-sepolia.example",
        deployments_dir=base,
    )
    assert surface.chain_id == 421_614
    assert surface.venue_address == "0xBfC91D59fdAA134A4ED45f7B584cAf96D7792Eff"
    assert surface.venue_real == "0xBfC91D59fdAA134A4ED45f7B584cAf96D7792Eff"
    assert surface.venue_mock == "0x5555555555555555555555555555555555555555"
    assert surface.strategy_vault_yield_rotation == ("0x6666666666666666666666666666666666666666")


def test_load_chain_surface_kite_default_real_is_swap_router(tmp_path: Path) -> None:
    base = _write_deployments(tmp_path)
    surface = load_chain_surface(
        ChainTarget.KITE_TESTNET,
        rpc_url="https://kite.example",
        deployments_dir=base,
    )
    assert surface.chain_id == 2368
    assert surface.venue_mode == VenueMode.REAL
    assert surface.venue_address == "0x55782e7019f4619a06a25bf66d2998c8fe2cc436"
    # Phase-3 Kite JSON has no LZ EID yet; default is zero.
    assert surface.lz_local_eid == 0


def test_load_chain_surface_missing_file(tmp_path: Path) -> None:
    base = tmp_path / "deployments"
    base.mkdir()
    with pytest.raises(DeploymentNotFoundError):
        load_chain_surface(
            ChainTarget.BASE_SEPOLIA,
            rpc_url="https://x",
            deployments_dir=base,
        )


def test_load_chain_surface_chain_id_mismatch_rejected(tmp_path: Path) -> None:
    base = tmp_path / "deployments"
    base.mkdir()
    (base / "base-sepolia.json").write_text(
        json.dumps(
            {
                "chainId": 1,  # wrong
                "addresses": {
                    "swapRouter": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "mockSwapRouter": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                },
            }
        )
    )
    with pytest.raises(ValueError, match="chainId mismatch"):
        load_chain_surface(
            ChainTarget.BASE_SEPOLIA,
            rpc_url="https://x",
            deployments_dir=base,
        )


def test_load_chain_surface_missing_venue_address_rejected(tmp_path: Path) -> None:
    base = tmp_path / "deployments"
    base.mkdir()
    (base / "base-sepolia.json").write_text(
        json.dumps(
            {
                "chainId": 84_532,
                "addresses": {
                    "swapRouter": "",  # blank real address
                    "mockSwapRouter": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                },
            }
        )
    )
    with pytest.raises(ValueError, match="venue address missing"):
        load_chain_surface(
            ChainTarget.BASE_SEPOLIA,
            venue_mode=VenueMode.REAL,
            rpc_url="https://x",
            deployments_dir=base,
        )
    # Mock mode resolves fine on the same JSON.
    surface = load_chain_surface(
        ChainTarget.BASE_SEPOLIA,
        venue_mode=VenueMode.MOCK,
        rpc_url="https://x",
        deployments_dir=base,
    )
    assert surface.venue_address == "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
