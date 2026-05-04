"""Witness builder — shape, padding, slippage, direction selectors.

Real Poseidon hashes are computed on the prover side (`circomlibjs`);
the builder leaves `oracle_root`, `params_hash`, and `trade_hash` as
placeholder zeros. These tests verify everything *else* lines up with
`mean_reversion_v1.circom` + `StrategyVault.PI_*` indexing.
"""

from __future__ import annotations

import pytest
from helios.types import Direction, TradeIntent
from mean_reversion_v1.witness import PRICE_OBSERVATIONS, build_mean_reversion_witness

_UNIVERSE_SYMBOLS = ("USDC", "WKITE", "WETH", "WBTC", "PAD4", "PAD5", "PAD6", "PAD7")
_UNIVERSE_ADDRS = [f"0x{i:040x}" for i in range(1, 9)]
_ASSET_IDX = {sym: i for i, sym in enumerate(_UNIVERSE_SYMBOLS)}


def _intent(**overrides: object) -> TradeIntent:
    base: dict[str, object] = dict(
        asset_in="USDC",
        asset_out="WETH",
        direction=Direction.LONG,
        amount_in_usd=1000.0,
        max_slippage_bps=50,
    )
    base.update(overrides)
    return TradeIntent(**base)  # type: ignore[arg-type]


def _build(**overrides: object):
    base: dict[str, object] = dict(
        intent=_intent(),
        asset_to_universe_idx=_ASSET_IDX,
        asset_universe_addresses=_UNIVERSE_ADDRS,
        price_observations_e18=[2000 * 10**18] * 16,
        declared_class_field=0xABCDEF,
        strategy_vault_address="0x" + "ee" * 20,
        allocator_address="0x" + "11" * 20,
        nonce=42,
        block_window_start=100,
        block_window_end=150,
        max_position_size_e18=10_000 * 10**18,
        max_slippage_bps=50,
        n_sigma_x100=200,
        stop_loss_price_e18=0,
        is_signal_flip=False,
        is_stop_loss=False,
    )
    base.update(overrides)
    return build_mean_reversion_witness(**base)  # type: ignore[arg-type]


def test_long_entry_selectors_one_hot() -> None:
    req = _build()
    inp = req.inputs
    assert inp["is_long_entry"] == "1"
    assert inp["is_short_entry"] == "0"
    assert inp["is_exit"] == "0"
    assert inp["trade_direction"] == "1"


def test_short_entry_selectors_one_hot() -> None:
    req = _build(
        intent=_intent(asset_in="WETH", asset_out="USDC", direction=Direction.SHORT),
    )
    inp = req.inputs
    assert inp["is_long_entry"] == "0"
    assert inp["is_short_entry"] == "1"
    assert inp["is_exit"] == "0"
    assert inp["trade_direction"] == "2"


def test_exit_requires_reason() -> None:
    with pytest.raises(ValueError, match="exit must specify"):
        _build(intent=_intent(direction=Direction.EXIT, amount_in_usd=500.0))


def test_exit_with_signal_flip_passes() -> None:
    req = _build(
        intent=_intent(direction=Direction.EXIT, amount_in_usd=500.0),
        is_signal_flip=True,
    )
    assert req.inputs["is_exit"] == "1"
    assert req.inputs["is_signal_flip"] == "1"
    assert req.inputs["is_stop_loss"] == "0"


def test_exit_with_stop_loss_passes() -> None:
    req = _build(
        intent=_intent(direction=Direction.EXIT, amount_in_usd=500.0),
        is_stop_loss=True,
        stop_loss_price_e18=950 * 10**18,
    )
    assert req.inputs["is_exit"] == "1"
    assert req.inputs["is_stop_loss"] == "1"
    assert req.inputs["is_signal_flip"] == "0"
    assert int(req.inputs["stop_loss_price"]) == 950 * 10**18


def test_exit_cannot_set_both_reasons() -> None:
    with pytest.raises(ValueError, match="cannot both be set"):
        _build(
            intent=_intent(direction=Direction.EXIT, amount_in_usd=500.0),
            is_signal_flip=True,
            is_stop_loss=True,
        )


def test_exit_reason_rejected_on_non_exit() -> None:
    with pytest.raises(ValueError, match="non-exit"):
        _build(is_signal_flip=True)


def test_amount_in_usd_scaled_to_e18() -> None:
    req = _build(intent=_intent(amount_in_usd=1234.5))
    assert int(req.inputs["amount_in"]) == int(1234.5 * 10**18)


def test_min_amount_out_respects_slippage() -> None:
    req = _build(intent=_intent(amount_in_usd=1000.0, max_slippage_bps=100))
    expected = (1000 * 10**18) * (10_000 - 100) // 10_000
    assert int(req.inputs["min_amount_out"]) == expected


def test_window_over_100_blocks_rejected() -> None:
    with pytest.raises(ValueError, match="block window > 100"):
        _build(block_window_start=100, block_window_end=300)


def test_universe_size_enforced() -> None:
    with pytest.raises(ValueError, match="must be 8 entries"):
        _build(asset_universe_addresses=_UNIVERSE_ADDRS[:7])


def test_asset_must_be_in_universe() -> None:
    with pytest.raises(ValueError, match="not in universe"):
        _build(intent=_intent(asset_out="MISSING"))


def test_price_observations_padded_to_16() -> None:
    req = _build(price_observations_e18=[1500 * 10**18, 1505 * 10**18, 1510 * 10**18])
    obs = req.inputs["price_observations"]
    assert len(obs) == PRICE_OBSERVATIONS
    # Left-padded with the oldest tick repeating.
    assert obs[0] == str(1500 * 10**18)
    assert obs[-1] == str(1510 * 10**18)


def test_signal_threshold_is_n_sigma_x100() -> None:
    req = _build(n_sigma_x100=275)
    assert req.inputs["signal_threshold"] == "275"


def test_oracle_root_params_hash_trade_hash_pending() -> None:
    """The prover service computes Poseidon for all three. Each lands as
    placeholder '0' in the request payload."""
    req = _build()
    assert req.inputs["oracle_root"] == "0"
    assert req.inputs["trade_hash"] == "0"
    assert req.inputs["params_hash"] == "0"
    assert req.pending_poseidon == ("oracle_root", "trade_hash", "params_hash")


def test_strategy_vault_addr_encoded_as_field() -> None:
    req = _build(strategy_vault_address="0x" + "ee" * 20)
    expected = int("ee" * 20, 16)
    assert int(req.inputs["strategy_vault"]) == expected


def test_asset_indices_use_universe_position() -> None:
    req = _build()
    assert req.inputs["asset_in_idx"] == str(_ASSET_IDX["USDC"])
    assert req.inputs["asset_out_idx"] == str(_ASSET_IDX["WETH"])


def test_amount_in_asset_uses_last_price() -> None:
    req = _build(
        intent=_intent(
            asset_in="WETH",
            asset_out="USDC",
            direction=Direction.EXIT,
            amount_in_usd=None,
            amount_in_asset=0.5,
        ),
        is_signal_flip=True,
        price_observations_e18=[2000 * 10**18] * 16,
    )
    assert int(req.inputs["amount_in"]) == int(0.5 * 2000 * 10**18)
