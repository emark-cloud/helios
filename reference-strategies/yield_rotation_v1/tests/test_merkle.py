"""Vector-parity test: Python Poseidon-Merkle ↔ circomlibjs.

Locks the yield-tree + allowlist-tree roots produced by `merkle.py`
against the canonical fixture in `circuits/scripts/gen-fixture-yr.js`
(also reproduced in `contracts/test/fixtures/yield_rotation_v1.json`'s
publicSignals[5] for the yield root).

The trade_hash check transitively asserts the allowlist root matches
too — Poseidon over those 11 fields fixes both roots.
"""

from __future__ import annotations

from helios.poseidon import poseidon_hash
from yield_rotation_v1.merkle import (
    build_allowlist_tree,
    build_yield_tree,
    inclusion_proof,
)

# Canonical fixture inputs from gen-fixture-yr.js
MARKETS = {
    "AAVE_USDC": 1,
    "COMPOUND_USDC": 2,
    "AAVE_USDT": 3,
    "COMPOUND_USDT": 4,
}
ALLOWLISTED = [
    MARKETS["AAVE_USDC"],
    MARKETS["COMPOUND_USDC"],
    MARKETS["AAVE_USDT"],
    MARKETS["COMPOUND_USDT"],
]
YIELD_SNAPSHOTS = [
    (MARKETS["AAVE_USDC"], 420),
    (MARKETS["COMPOUND_USDC"], 550),
    (MARKETS["AAVE_USDT"], 380),
    (MARKETS["COMPOUND_USDT"], 500),
]

# publicSignals[5] from contracts/test/fixtures/yield_rotation_v1.json
EXPECTED_YIELD_ROOT = 19617008100108992903905573385623852931387633461552456891295159462318722212376
# publicSignals[0]
EXPECTED_TRADE_HASH = 20663455979481276034561464138722727257422408101475448626751031931004162363337


def test_yield_tree_root_matches_js_fixture() -> None:
    tree = build_yield_tree(YIELD_SNAPSHOTS, depth=6)
    assert tree.root == EXPECTED_YIELD_ROOT


def test_allowlist_tree_root_consistent_with_trade_hash() -> None:
    """Allowlist root isn't directly emitted as a public signal but it
    feeds trade_hash. Reconstruct trade_hash and assert parity."""
    yield_tree = build_yield_tree(YIELD_SNAPSHOTS, depth=6)
    allow_tree = build_allowlist_tree(ALLOWLISTED, depth=4)

    declared_class = 0x9ABC  # 39612
    m_from = MARKETS["AAVE_USDC"]
    m_to = MARKETS["COMPOUND_USDC"]
    amount_rotating = 10**18
    allocator_address = 0xA11CA7  # 10558631
    nonce = 7
    block_window_end = 200
    signal_threshold = 80
    bridging_cost = 30

    trade_hash = poseidon_hash(
        [
            declared_class,
            m_from,
            m_to,
            amount_rotating,
            yield_tree.root,
            allocator_address,
            nonce,
            block_window_end,
            signal_threshold,
            bridging_cost,
            allow_tree.root,
        ]
    )
    assert trade_hash == EXPECTED_TRADE_HASH


def test_inclusion_proof_recovers_root_yield() -> None:
    tree = build_yield_tree(YIELD_SNAPSHOTS, depth=6)
    # AAVE_USDC sits at index 0
    proof = inclusion_proof(tree, 0)
    assert len(proof.path_indices) == 6
    assert len(proof.siblings) == 6
    # Recompute root by hashing leaf up the path
    leaf = tree.levels[0][0]
    cur = leaf
    for path_bit, sib in zip(proof.path_indices, proof.siblings, strict=True):
        cur = poseidon_hash([cur, sib]) if path_bit == 0 else poseidon_hash([sib, cur])
    assert cur == tree.root


def test_inclusion_proof_recovers_root_allowlist() -> None:
    tree = build_allowlist_tree(ALLOWLISTED, depth=4)
    proof = inclusion_proof(tree, 1)  # COMPOUND_USDC
    cur = tree.levels[0][1]
    for path_bit, sib in zip(proof.path_indices, proof.siblings, strict=True):
        cur = poseidon_hash([cur, sib]) if path_bit == 0 else poseidon_hash([sib, cur])
    assert cur == tree.root


def test_yield_tree_padding_at_full_capacity() -> None:
    """Padding leaf is Poseidon([0,0]); test that 4 real entries + 60
    pads gives the expected canonical root."""
    full = build_yield_tree(YIELD_SNAPSHOTS, depth=6)
    pad = poseidon_hash([0, 0])
    # Each unfilled leaf hashes to `pad`; first level after 64 leaves
    # has 32 entries. Just sanity check that pad shows up at index 4+.
    assert full.levels[0][4] == pad
    assert full.levels[0][63] == pad


def test_allowlist_tree_too_many_leaves_rejected() -> None:
    import pytest

    with pytest.raises(ValueError, match="too many"):
        build_allowlist_tree([i + 1 for i in range(17)], depth=4)
