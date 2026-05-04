"""Pure-Python Poseidon — bit-exact parity with circomlibjs / circom.

Strategy authors building witnesses for `momentum_v1`, `mean_reversion_v1`,
and `yield_rotation_v1` need to compute a few Poseidon-bound public inputs
locally (`params_hash`, `oracle_root`, `trade_hash`). Shelling out to
Node.js (which the oracle service does for its own snapshot chain) adds a
runtime dependency that the SDK can't impose on external operators
installing the wheel from PyPI — see `project_strategy_sdk_distribution`.

This module wraps `circomlibpy` (a small pure-Python BN254 Poseidon that
mirrors `iden3/circomlibjs`'s constants table-for-table). Bit-exact parity
is exercised in `tests/test_poseidon.py` against the same fixture values
the on-chain Foundry round-trip tests consume — so any drift between this
module and the deployed verifier is caught as a unit-test failure rather
than as an on-chain rejection.

Public API:

  - `FIELD_MODULUS`: BN254 scalar field modulus.
  - `poseidon_hash(inputs)`: sponge over `inputs`, returns the squeezed
    field element.
  - `poseidon_chain(inputs)`: matches the `chained` helper in
    `circuits/scripts/gen-fixture.js` — `h0 = P([x0])`, `hi = P([h_{i-1},
    xi])`. Used by the momentum / mean-reversion circuits as the
    `oracle_root` over a 16-bar price window.
"""

from __future__ import annotations

from helios._vendor.circomlibpy.poseidon import PoseidonHash

FIELD_MODULUS = 21888242871839275222246405745257275088548364400416034343698204186575808495617

_HASHER = PoseidonHash()


def poseidon_hash(inputs: list[int]) -> int:
    """Poseidon over `inputs` (1..16 BN254 field elements). Each input is
    reduced mod `FIELD_MODULUS` before hashing, matching circomlibjs.
    """
    if not inputs:
        raise ValueError("poseidon_hash requires at least one input")
    if len(inputs) > 16:
        raise ValueError("poseidon_hash supports up to 16 inputs (circomlibjs limit)")
    reduced = [int(x) % FIELD_MODULUS for x in inputs]
    return _HASHER.hash(len(reduced), reduced)


def poseidon_chain(inputs: list[int]) -> int:
    """Linear Poseidon chain matching `chained` in
    `circuits/scripts/gen-fixture.js`:

        h_0 = poseidon_hash([x_0])
        h_i = poseidon_hash([h_{i-1}, x_i])  for i ≥ 1

    Used by the `momentum_v1` / `mean_reversion_v1` circuits to fold the
    16-bar `price_observations` window into a single `oracle_root`. Other
    chain shapes (e.g. yield_rotation_v1's depth-N Merkle) compose
    `poseidon_hash` directly.
    """
    if not inputs:
        raise ValueError("poseidon_chain requires at least one input")
    h = poseidon_hash([inputs[0]])
    for x in inputs[1:]:
        h = poseidon_hash([h, x])
    return h


def address_to_field(addr: str) -> int:
    """Lower-cased hex address (`0x…`) → BN254 field element (uint160 fits)."""
    if not (addr.startswith("0x") or addr.startswith("0X")):
        raise ValueError(f"expected hex address, got: {addr!r}")
    return int(addr, 16)
