"""Witness builder — shape, padding, slippage, direction selectors, and
computed Poseidon completions.

Bit-exact Poseidon parity against the on-chain fixture is exercised in
`packages/strategy-sdk/tests/test_poseidon.py`. These tests assert the
builder wires those Poseidon outputs into the witness payload at the
correct keys and that the surrounding shape matches `momentum_v1.circom`
+ `StrategyVault.PI_*` indexing.
"""

from __future__ import annotations

import pytest
from helios.poseidon import poseidon_chain, poseidon_hash
from helios.types import Direction, TradeIntent
from momentum_v1.witness import PRICE_OBSERVATIONS, build_momentum_witness

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
        signal_threshold_bps=150,
        position_state_e18=0,
        stop_loss_price_e18=0,
        is_signal_flip=False,
        is_stop_loss=False,
    )
    base.update(overrides)
    return build_momentum_witness(**base)  # type: ignore[arg-type]


def test_long_entry_selectors_one_hot() -> None:
    req = _build()
    inp = req.inputs
    assert inp["is_long_entry"] == "1"
    assert inp["is_short_entry"] == "0"
    assert inp["is_exit"] == "0"
    assert inp["trade_direction"] == "1"


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


def test_params_hash_oracle_root_trade_hash_computed() -> None:
    """Builder ships fully-populated Poseidon completions — no
    placeholder zeros (the prover service does not do server-side
    fixup; placeholders would land as a verifier reject)."""
    req = _build()
    inp = req.inputs

    expected_params_hash = poseidon_hash(
        [int(inp["max_position_size"]), 50, 150, int(inp["stop_loss_price"])]
    )
    assert int(inp["params_hash"]) == expected_params_hash
    assert req.params_hash == expected_params_hash.to_bytes(32, "big")

    expected_oracle_root = poseidon_chain([int(p) for p in inp["price_observations"]])
    assert int(inp["oracle_root"]) == expected_oracle_root
    assert req.oracle_root == expected_oracle_root.to_bytes(32, "big")

    expected_trade_hash = poseidon_hash(
        [
            int(inp["strategy_vault"]),
            int(inp["declared_class"]),
            expected_params_hash,
            int(inp["allocator_address"]),
            int(inp["asset_in_idx"]),
            int(inp["asset_out_idx"]),
            int(inp["amount_in"]),
            int(inp["min_amount_out"]),
            int(inp["trade_direction"]),
            int(inp["nonce"]),
        ]
    )
    assert int(inp["trade_hash"]) == expected_trade_hash
    assert req.trade_hash == expected_trade_hash.to_bytes(32, "big")


def test_strategy_vault_addr_encoded_as_field() -> None:
    req = _build(strategy_vault_address="0x" + "ee" * 20)
    assert int(req.inputs["strategy_vault"]) == int("ee" * 20, 16)


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


def test_fixture_round_trip() -> None:
    """Cross-check against the on-chain fixture
    (`circuits/scripts/gen-fixture.js` knobs):
    strategy_vault=0xbeef00, allocator=0xa11ca7, declared_class=0x1234,
    16 bars of 1000+i*5, signal_threshold=100bps, params bounds match
    the fixture defaults. The witness's three Poseidon outputs must equal
    the fixture's `publicSignals[0]` (trade_hash), `publicSignals[3]`
    (params_hash), and `publicSignals[13]` (oracle_root).
    """
    req = build_momentum_witness(
        intent=TradeIntent(
            asset_in="USDC",
            asset_out="WBTC",  # idx=3
            direction=Direction.LONG,
            amount_in_usd=1.0,  # → 1e18
            max_slippage_bps=50,
        ),
        asset_to_universe_idx=_ASSET_IDX,
        asset_universe_addresses=_UNIVERSE_ADDRS,
        price_observations_e18=[1000 + i * 5 for i in range(16)],
        declared_class_field=0x1234,
        strategy_vault_address="0xbeef00",
        allocator_address="0xa11ca7",
        nonce=42,
        block_window_start=100,
        block_window_end=150,
        max_position_size_e18=5 * 10**18,
        max_slippage_bps=50,
        signal_threshold_bps=100,
        position_state_e18=0,
        stop_loss_price_e18=0,
        is_signal_flip=False,
        is_stop_loss=False,
    )
    assert (
        int(req.inputs["params_hash"])
        == 15156193349259122427382123461171905084636555227186025438992819655662310206953
    )
    assert (
        int(req.inputs["oracle_root"])
        == 19227955533869764475997746616829700814890964403601080078384715274766485910570
    )
    assert (
        int(req.inputs["trade_hash"])
        == 3003122794127521053123681721578845572260160476947025219414413002822614285464
    )
