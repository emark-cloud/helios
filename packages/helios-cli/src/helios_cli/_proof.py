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

    Operators may pass either the human name (`"momentum_v1"`) or a
    0x-prefixed hex string. Names are right-padded to 32 bytes (matches
    the contracts' `bytes32("momentum_v1")`-style class IDs)."""
    if declared_class.startswith("0x"):
        raw = bytes.fromhex(declared_class[2:])
        if len(raw) > 32:
            raise ValueError(f"declared_class {declared_class} > 32 bytes")
        return raw.rjust(32, b"\x00") if len(raw) < 32 else raw
    encoded = declared_class.encode("ascii")
    if len(encoded) > 32:
        raise ValueError(f"declared_class {declared_class!r} > 32 bytes")
    return encoded.ljust(32, b"\x00")


__all__ = ["class_to_bytes32", "proof_to_bytes", "public_signals_to_uints"]
