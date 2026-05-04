"""`helios.poseidon` — bit-exact parity tests against on-chain fixtures.

Each constant in this file comes from the JSON fixtures under
`contracts/test/fixtures/{momentum,mean_reversion}_v1.json`, which the
Foundry round-trip tests use to verify Groth16 proofs against the
deployed verifiers. Drift between this module and the fixtures means the
SDK's witness builders would emit a witness the on-chain verifier
rejects — so the unit test is the same gate as the e2e proof, just
compiled into pytest.

Inputs to the fixtures themselves come from
`circuits/scripts/gen-fixture.js` (momentum) and
`circuits/scripts/gen-fixture-mr.js` (mean reversion).
"""

from __future__ import annotations

import pytest
from helios.poseidon import (
    FIELD_MODULUS,
    address_to_field,
    poseidon_chain,
    poseidon_hash,
)

# ----- momentum_v1 fixture -------------------------------------------------
# gen-fixture.js: max_position_size=5e18, max_slippage_bps=50,
# signal_threshold=100, stop_loss_price=0.
_MOMENTUM_PARAMS_HASH = (
    15156193349259122427382123461171905084636555227186025438992819655662310206953
)

# gen-fixture.js: strategy_vault=0xbeef00, declared_class=0x1234,
# allocator_address=0xa11ca7, asset_in_idx=0, asset_out_idx=3,
# amount_in=1e18, min_amount_out=995e15, trade_direction=1, nonce=42.
_MOMENTUM_TRADE_HASH = 3003122794127521053123681721578845572260160476947025219414413002822614285464

# 16 bars: 1000, 1005, ..., 1075.
_MOMENTUM_ORACLE_ROOT = (
    19227955533869764475997746616829700814890964403601080078384715274766485910570
)

# ----- mean_reversion_v1 fixture -------------------------------------------
# gen-fixture-mr.js: same bounds, signal_threshold=200 (= 2.00σ).
_MR_PARAMS_HASH = 12441673086156183748057805468196993645378568675500367430807514580524230758459

# 15 bars at 1000, last bar at 700.
_MR_ORACLE_ROOT = 15960622218484124943527498354244336609744278190070709384187159996542471155407

# Same vault/allocator/idx tuple as momentum, declared_class=0x5678.
_MR_TRADE_HASH = 17790372904353956429098291626594131965871939508489099441957090224480872231583


def test_field_modulus_is_bn254_scalar() -> None:
    assert (
        FIELD_MODULUS
        == 21888242871839275222246405745257275088548364400416034343698204186575808495617
    )


def test_momentum_params_hash_matches_fixture() -> None:
    assert poseidon_hash([5 * 10**18, 50, 100, 0]) == _MOMENTUM_PARAMS_HASH


def test_momentum_trade_hash_matches_fixture() -> None:
    th = poseidon_hash(
        [
            0xBEEF00,
            0x1234,
            _MOMENTUM_PARAMS_HASH,
            0xA11CA7,
            0,
            3,
            10**18,
            995 * 10**15,
            1,
            42,
        ]
    )
    assert th == _MOMENTUM_TRADE_HASH


def test_momentum_oracle_root_matches_fixture() -> None:
    obs = [1000 + i * 5 for i in range(16)]
    assert poseidon_chain(obs) == _MOMENTUM_ORACLE_ROOT


def test_mean_reversion_params_hash_matches_fixture() -> None:
    assert poseidon_hash([5 * 10**18, 50, 200, 0]) == _MR_PARAMS_HASH


def test_mean_reversion_trade_hash_matches_fixture() -> None:
    th = poseidon_hash(
        [
            0xBEEF00,
            0x5678,
            _MR_PARAMS_HASH,
            0xA11CA7,
            0,
            3,
            10**18,
            995 * 10**15,
            1,
            42,
        ]
    )
    assert th == _MR_TRADE_HASH


def test_mean_reversion_oracle_root_matches_fixture() -> None:
    obs = [1000] * 15 + [700]
    assert poseidon_chain(obs) == _MR_ORACLE_ROOT


def test_poseidon_hash_rejects_empty() -> None:
    with pytest.raises(ValueError, match="at least one input"):
        poseidon_hash([])


def test_poseidon_hash_rejects_overflow_count() -> None:
    with pytest.raises(ValueError, match="up to 16 inputs"):
        poseidon_hash(list(range(17)))


def test_poseidon_chain_rejects_empty() -> None:
    with pytest.raises(ValueError, match="at least one input"):
        poseidon_chain([])


def test_poseidon_chain_single_input_equals_hash() -> None:
    assert poseidon_chain([42]) == poseidon_hash([42])


def test_address_to_field_strips_prefix() -> None:
    assert address_to_field("0xbeef00") == 0xBEEF00
    assert address_to_field("0x" + "a1" * 20) == int("a1" * 20, 16)


def test_address_to_field_rejects_non_hex() -> None:
    with pytest.raises(ValueError, match="hex address"):
        address_to_field("beef")


def test_inputs_above_modulus_are_reduced() -> None:
    """Mirror circomlibjs: each input is reduced into the BN254 scalar
    field before hashing. `x` and `x + FIELD_MODULUS` must produce the
    same digest."""
    a = poseidon_hash([42])
    b = poseidon_hash([42 + FIELD_MODULUS])
    assert a == b
