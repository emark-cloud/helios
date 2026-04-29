"""Vector-parity tests for `oracle.poseidon`.

Locks the Python wrapper to bit-exact equivalence with the chained
Poseidon used in `circuits/momentum_v1.circom:127-138` and asserted by
`circuits/test/momentum_v1.test.js:36-43`.

If circomlibjs is bumped, `lib_pos.so` is replaced, or constants drift,
these vectors will fail before any circuit witness fails — that's the
point. The fixtures here are derived directly by running the helper, so
the test verifies the wrapper relays bytes correctly AND that the helper
agrees with the canonical circuit witness.

The "circuit-known-good" vector below is the chained Poseidon over the
exact 16-bar series in `momentum_v1.test.js` `buildValidInput()`
(prices 1000, 1005, ..., 1075). If you change that fixture in the
circuit test, regenerate it here.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from oracle.poseidon import (
    FIELD_MODULUS,
    PoseidonClient,
    poseidon_chain,
    poseidon_hash,
)

# Chained Poseidon over [1000, 1005, ..., 1075] — the canonical
# `momentum_v1.test.js` `buildValidInput` price series. Computed via
# `node scripts/poseidon_helper.js` against circomlibjs 0.1.7. If this
# value changes, the momentum circuit's accepted witnesses change too.
MOMENTUM_FIXTURE_ROOT = (
    "19227955533869764475997746616829700814890964403601080078384715274766485910570"
)


@pytest.fixture(scope="module")
def client() -> Generator[PoseidonClient, None, None]:
    c = PoseidonClient()
    yield c
    c.close()


def test_hash_two_inputs_matches_circomlibjs(client: PoseidonClient) -> None:
    # P(1, 2) — well-known circomlibjs reference value.
    out = client.hash([1, 2])
    assert out == 7853200120776062878684798364095072458815029376092732009249414926327459813530


def test_hash_single_input_zero(client: PoseidonClient) -> None:
    # Boundary: zero is a valid field element. P(0) is well-defined.
    out = client.hash([0])
    assert 0 < out < FIELD_MODULUS


def test_chain_single_input_equals_hash(client: PoseidonClient) -> None:
    # Chain protocol: h0 = P(x0). With one input, chain == hash.
    assert client.chain([42]) == client.hash([42])


def test_chain_matches_momentum_circuit_fixture(client: PoseidonClient) -> None:
    """Lock parity with `circuits/test/momentum_v1.test.js:64-77`."""
    prices = [1000 + i * 5 for i in range(16)]
    assert str(client.chain(prices)) == MOMENTUM_FIXTURE_ROOT


def test_chain_associativity_is_left_fold(client: PoseidonClient) -> None:
    # Spec invariant: chain([a, b, c]) == P(P(P(a)), b), c).
    a, b, c = 1, 2, 3
    h0 = client.hash([a])
    h1 = client.hash([h0, b])
    h2 = client.hash([h1, c])
    assert client.chain([a, b, c]) == h2


def test_chain_reduces_inputs_modulo_field(client: PoseidonClient) -> None:
    """Inputs >= p MUST reduce — circomlibjs does this internally and
    callers (price_e18) can in principle exceed p in pathological cases."""
    a = 7
    b = 7 + FIELD_MODULUS  # equivalent in the field
    assert client.chain([a]) == client.chain([b])


def test_chain_max_field_input(client: PoseidonClient) -> None:
    # Boundary: p-1 is the largest legal input.
    out = client.chain([FIELD_MODULUS - 1])
    assert 0 < out < FIELD_MODULUS


def test_module_level_singleton_works() -> None:
    # Sanity: module-level helpers wire to the same singleton.
    a = poseidon_hash([1, 2])
    b = poseidon_chain([1])  # h0 = P(1)
    assert a > 0 and b > 0


def test_empty_chain_rejected(client: PoseidonClient) -> None:
    with pytest.raises(ValueError):
        client.chain([])


def test_empty_hash_rejected(client: PoseidonClient) -> None:
    with pytest.raises(ValueError):
        client.hash([])
