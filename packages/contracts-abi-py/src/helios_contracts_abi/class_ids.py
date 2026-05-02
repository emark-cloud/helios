"""Strategy-class identifiers, pinned to the on-chain `ClassIds.sol` library.

Identical convention as Solidity (`contracts/src/ClassIds.sol`):

    id = Poseidon([int.from_bytes(<name>, "big")])

Encoded as a Poseidon hash so the value lands inside the BN254 scalar field
and snarkjs's `checkField` accepts it. `keccak256("momentum_v1")` and friends
are above the field modulus and would revert before any proof check ran —
see the comment in `ClassIds.sol`.

Drift between this module and `ClassIds.sol` is caught by the Foundry
`test/ClassIds.t.sol` parity test (re-derives the constants from the
canonical Python Poseidon helper via `vm.ffi`)."""

from __future__ import annotations

# bytes32 values, mirrored from contracts/src/ClassIds.sol.
MOMENTUM_V1: bytes = bytes.fromhex(
    "2a9aa442064b635baec37a7a259282faa5563a653a8325378d5676c6f04bc9dd"
)
MEAN_REVERSION_V1: bytes = bytes.fromhex(
    "18602f4f74172d545f5258541634e1a125c3a4e1227ee2a4cbee957d3490f1fb"
)
YIELD_ROTATION_V1: bytes = bytes.fromhex(
    "2e882135c6afc3bda02a9c8a7c6a351198d97599c804a2575a3d616073a87251"
)


# Mapping from the human-readable slug used by frontend filters, prover
# requests, and the spec to the on-chain bytes32 identifier.
SLUG_TO_BYTES32: dict[str, bytes] = {
    "momentum_v1": MOMENTUM_V1,
    "mean_reversion_v1": MEAN_REVERSION_V1,
    "yield_rotation_v1": YIELD_ROTATION_V1,
}

BYTES32_TO_SLUG: dict[bytes, str] = {v: k for k, v in SLUG_TO_BYTES32.items()}


def class_id_for_slug(slug: str) -> bytes:
    """Look up the canonical bytes32 class id for a slug. Raises on unknown."""
    try:
        return SLUG_TO_BYTES32[slug]
    except KeyError as exc:
        raise ValueError(f"unknown strategy class slug: {slug!r}") from exc


def class_id_as_field(slug: str) -> int:
    """Same as `class_id_for_slug` but returned as a uint256 field element
    suitable for circuit witness inputs and `executeWithProof` publicInputs."""
    return int.from_bytes(class_id_for_slug(slug), "big")


__all__ = [
    "MOMENTUM_V1",
    "MEAN_REVERSION_V1",
    "YIELD_ROTATION_V1",
    "SLUG_TO_BYTES32",
    "BYTES32_TO_SLUG",
    "class_id_for_slug",
    "class_id_as_field",
]
