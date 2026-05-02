"""`_proof` — snarkjs proof / class identifier helpers."""

from __future__ import annotations

import pytest
from helios_cli._proof import (
    class_to_bytes32,
    proof_to_bytes,
    public_signals_to_uints,
)


def test_proof_to_bytes_layout() -> None:
    proof = {
        "pi_a": ["1", "2", "1"],
        "pi_b": [["3", "4"], ["5", "6"], ["1", "0"]],
        "pi_c": ["7", "8", "1"],
    }
    packed = proof_to_bytes(proof)
    assert len(packed) == 256
    # Word ordering matches services' `_proof_to_bytes` reference encoder
    # (a.x, a.y, b.x.imag, b.x.real, b.y.imag, b.y.real, c.x, c.y).
    expected = [1, 2, 4, 3, 6, 5, 7, 8]
    for i, value in enumerate(expected):
        word = packed[i * 32 : (i + 1) * 32]
        assert int.from_bytes(word, "big") == value


def test_public_signals_to_uints() -> None:
    assert public_signals_to_uints(["1", "2", "999"]) == [1, 2, 999]


def test_class_to_bytes32_known_slug() -> None:
    # Mirrors contracts/src/ClassIds.sol — Poseidon-derived, BN254-fit.
    out = class_to_bytes32("momentum_v1")
    assert len(out) == 32
    assert out.hex() == "2a9aa442064b635baec37a7a259282faa5563a653a8325378d5676c6f04bc9dd"


def test_class_to_bytes32_unknown_slug_rejected() -> None:
    with pytest.raises(ValueError, match="unknown class slug"):
        class_to_bytes32("non_existent_class")


def test_class_to_bytes32_hex() -> None:
    out = class_to_bytes32("0x" + "00" * 30 + "0102")
    assert len(out) == 32
    assert out[-2:] == b"\x01\x02"


def test_class_to_bytes32_too_long() -> None:
    with pytest.raises(ValueError):
        class_to_bytes32("0x" + "ff" * 33)
