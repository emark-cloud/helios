"""Snarkjs proof helpers.

The prover service returns a Groth16 proof in snarkjs JSON shape:

    { "pi_a": [...], "pi_b": [[...],[...],...], "pi_c": [...] }

`TradeAttestationVerifier.verify(declaredClass, proof, publicInputs)`
expects `proof` as 256 bytes — the abi-encoding of `uint256[8]` —
and `publicInputs` as a `uint256[]`. This module mirrors the encoder
the reference momentum runtime uses (`runtime._proof_to_bytes`) so
the CLI's `helios test-proof` round-trips identically."""

from __future__ import annotations

from typing import Any

from helios_contracts_abi.class_ids import SLUG_TO_BYTES32


def proof_to_bytes(proof: dict[str, Any]) -> bytes:
    """Pack a snarkjs Groth16 proof into the 256-byte form the
    Solidity verifier accepts: 8 × uint256 (a.x, a.y, b.x.imag,
    b.x.real, b.y.imag, b.y.real, c.x, c.y)."""
    pa = [int(x) for x in proof["pi_a"][:2]]
    pb_x = [int(x) for x in proof["pi_b"][0]]
    pb_y = [int(x) for x in proof["pi_b"][1]]
    pc = [int(x) for x in proof["pi_c"][:2]]
    words = [
        *pa,
        pb_x[1],
        pb_x[0],
        pb_y[1],
        pb_y[0],
        *pc,
    ]
    return b"".join(w.to_bytes(32, "big") for w in words)


def public_signals_to_uints(public_signals: list[str]) -> list[int]:
    return [int(s) for s in public_signals]


def class_to_bytes32(declared_class: str) -> bytes:
    """`bytes32` encoding of a class identifier.

    Operators may pass either a known class slug (`"momentum_v1"`,
    `"mean_reversion_v1"`, `"yield_rotation_v1"`) — looked up in
    `helios_contracts_abi.class_ids.SLUG_TO_BYTES32` — or a 0x-prefixed
    hex string for one-off / advanced use. Class IDs MUST be the
    Poseidon-derived bytes32 from `contracts/src/ClassIds.sol` so the
    Groth16 verifier's `checkField` accepts them — see the comment on
    that library for why keccak doesn't fit."""
    if declared_class.startswith("0x"):
        raw = bytes.fromhex(declared_class[2:])
        if len(raw) > 32:
            raise ValueError(f"declared_class {declared_class} > 32 bytes")
        return raw.rjust(32, b"\x00") if len(raw) < 32 else raw
    if declared_class in SLUG_TO_BYTES32:
        return SLUG_TO_BYTES32[declared_class]
    raise ValueError(
        f"unknown class slug {declared_class!r}; pass a known slug or a 0x-prefixed bytes32"
    )


__all__ = ["class_to_bytes32", "proof_to_bytes", "public_signals_to_uints"]
