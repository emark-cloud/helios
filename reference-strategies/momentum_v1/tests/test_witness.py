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
    # Cross-decimal slippage (Phase-6 Constraint 2). Default fixture is
    # LONG USDC→WETH at $2000 / WETH, both 18-dec when asset_decimals
    # is unset. expected_weth = $1000 / $2000 = 0.5 WETH = 5e17 wei.
    req = _build(intent=_intent(amount_in_usd=1000.0, max_slippage_bps=100))
    pow10_in = 10**18
    pow10_out = 10**18
    amount_in = 1000 * 10**18
    price = 2000 * 10**18
    expected = (amount_in * pow10_out * 10**18) // (pow10_in * price)
    min_out = (expected * 9_900 + 9_999) // 10_000
    assert int(req.inputs["expected_amount_out"]) == expected
    assert int(req.inputs["min_amount_out"]) == min_out


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
    16 bars of (1000+i*5)e18, signal_threshold=100bps. The witness's
    Poseidon outputs (and the new pow10 + min_amount_out fields) must
    equal the fixture's publicSignals. Prices are e18-scaled to match
    the production oracle convention; the cross-decimal Constraint 2
    requires `expected_amount_out` fit in 96 bits, which raw prices
    blow."""
    import json
    from pathlib import Path

    fixture = json.loads(
        Path("contracts/test/fixtures/momentum_v1.json").read_text()
    )
    pub = fixture["publicSignals"]
    e18 = 10**18
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
        price_observations_e18=[(1000 + i * 5) * e18 for i in range(16)],
        declared_class_field=0x1234,
        strategy_vault_address="0xbeef00",
        allocator_address="0xa11ca7",
        nonce=42,
        block_window_start=100,
        block_window_end=150,
        max_position_size_e18=5 * e18,
        max_slippage_bps=50,
        signal_threshold_bps=100,
        stop_loss_price_e18=0,
        is_signal_flip=False,
        is_stop_loss=False,
    )
    assert int(req.inputs["trade_hash"]) == int(pub[0])
    assert int(req.inputs["params_hash"]) == int(pub[3])
    assert int(req.inputs["oracle_root"]) == int(pub[13])
    assert int(req.inputs["pow10_asset_in"]) == int(pub[14])
    assert int(req.inputs["pow10_asset_out"]) == int(pub[15])
    assert int(req.inputs["amount_in"]) == int(pub[7])
    assert int(req.inputs["min_amount_out"]) == int(pub[8])


# ── Multi-decimal mode (Phase-6 real-P&L) ────────────────────────────


def test_multi_decimal_long_entry_uses_stable_decimals() -> None:
    """LONG (USDC -> asset) with multi-decimal mode must scale
    `amount_in_usd` by USDC's raw decimals, NOT 10**18. Phase-6
    deploys mUSDC with 18-decimal MockERC20; mainnet-style USDC=6
    is also covered."""
    # mUSDC=18 case (current Kite testnet shape).
    req = _build(asset_decimals={"USDC": 18, "WETH": 18})
    assert int(req.inputs["amount_in"]) == 1000 * 10**18

    # USDC=6 case (real USDC on mainnet, future-proof).
    req6 = _build(asset_decimals={"USDC": 6, "WETH": 18})
    assert int(req6.inputs["amount_in"]) == 1000 * 10**6


def test_multi_decimal_exit_uses_asset_decimals() -> None:
    """EXIT (asset -> USDC) with multi-decimal mode must scale
    `amount_in_asset` by the asset's raw decimals, replacing the
    legacy `amount_in_asset * last_price_e18` shortcut. The PI_AMOUNT_IN
    that lands on chain MUST equal raw `tokenIn` units so the swap
    router amount-in check passes."""
    # Sell 0.001 WBTC (8 decimals) -> 100k raw satoshis.
    req = _build(
        intent=_intent(
            asset_in="WBTC",
            asset_out="USDC",
            direction=Direction.EXIT,
            amount_in_usd=None,
            amount_in_asset=0.001,
        ),
        is_signal_flip=True,
        asset_decimals={"USDC": 18, "WBTC": 8, "WETH": 18},
        # last_price_e18 is irrelevant in multi-decimal mode but the
        # builder still receives observations.
        price_observations_e18=[50_000 * 10**18] * 16,
    )
    assert int(req.inputs["amount_in"]) == int(0.001 * 10**8)


def test_multi_decimal_falls_back_to_legacy_for_unknown_asset() -> None:
    """If `asset_decimals` is provided but doesn't list `intent.asset_in`,
    the builder falls back to the legacy USD*10^18 encoding. Lets a
    partially-migrated config keep working without silent decimal
    mistakes for the assets it does cover."""
    req = _build(
        intent=_intent(amount_in_usd=42.0),
        asset_decimals={"WETH": 18},  # USDC missing — falls back.
    )
    assert int(req.inputs["amount_in"]) == 42 * 10**18  # legacy USD*10^18


def test_multi_decimal_min_amount_out_respects_slippage() -> None:
    """USDC (6-dec) → WETH (18-dec) LONG. `min_amount_out` is computed
    off the cross-decimal `expected_amount_out`, which the circuit
    pins to the exact floor of the price conversion."""
    req = _build(
        intent=_intent(amount_in_usd=1000.0, max_slippage_bps=100),
        asset_decimals={"USDC": 6, "WETH": 18},
    )
    expected_in = 1000 * 10**6
    pow10_in = 10**6
    pow10_out = 10**18
    price = 2000 * 10**18
    expected_weth = (expected_in * pow10_out * 10**18) // (pow10_in * price)
    expected_min_out = (expected_weth * 9_900 + 9_999) // 10_000
    assert int(req.inputs["amount_in"]) == expected_in
    assert int(req.inputs["expected_amount_out"]) == expected_weth
    assert int(req.inputs["min_amount_out"]) == expected_min_out
    assert req.inputs["pow10_asset_in"] == str(pow10_in)
    assert req.inputs["pow10_asset_out"] == str(pow10_out)
