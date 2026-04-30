"""Poseidon-Merkle tree builder for `yield_rotation_v1` witnesses.

The YR circuit needs four Merkle inclusion proofs each call:
  - `(m_from, apy_from)` against `yield_oracle_root` (depth 6 → 64 leaves)
  - `(m_to, apy_to)` against `yield_oracle_root`
  - `m_from` against `markets_allowlist_root` (depth 4 → 16 leaves)
  - `m_to` against `markets_allowlist_root`

Mirrors the JS reference in `circuits/scripts/gen-fixture-yr.js` line for
line so a Python-built witness yields the same root bytes as the JS
fixture. Vector parity is asserted in `tests/test_merkle.py` against the
canonical fixture inputs.

Padding: leaves are right-padded to the full `2**depth` count with a
class-specific zero leaf:
  - allowlist tree: `Poseidon([0])`
  - yield tree:     `Poseidon([0, 0])`

These match the on-chain `setMarketAllowlistRoot` convention and the
oracle's yield-tree builder (Phase 5 will surface the leaves directly via
`/v1/yield/leaves`; until then operators reconstruct).
"""

from __future__ import annotations

from dataclasses import dataclass

from oracle.poseidon import poseidon_hash


@dataclass(frozen=True, slots=True)
class MerkleTree:
    """Cached level-by-level representation. `levels[0]` is leaves;
    `levels[depth][0]` is the root."""

    levels: list[list[int]]

    @property
    def root(self) -> int:
        return self.levels[-1][0]

    @property
    def depth(self) -> int:
        return len(self.levels) - 1


@dataclass(frozen=True, slots=True)
class InclusionProof:
    """`path_indices[i] == 0` ⇒ sibling sits to the right at level i."""

    path_indices: list[int]
    siblings: list[int]


def build_poseidon_tree(leaves: list[int], depth: int) -> MerkleTree:
    """Build a perfectly balanced Poseidon binary tree.

    `leaves` must be exactly `2**depth` entries. Callers pad with the
    class-specific zero leaf before calling.
    """
    expected = 1 << depth
    if len(leaves) != expected:
        raise ValueError(f"expected {expected} leaves, got {len(leaves)}")
    levels: list[list[int]] = [list(leaves)]
    for d in range(depth):
        cur = levels[d]
        nxt: list[int] = []
        for i in range(0, len(cur), 2):
            nxt.append(poseidon_hash([cur[i], cur[i + 1]]))
        levels.append(nxt)
    return MerkleTree(levels=levels)


def inclusion_proof(tree: MerkleTree, index: int) -> InclusionProof:
    """Generate a Merkle inclusion proof for the leaf at `index`.

    Path bit semantics match `gen-fixture-yr.js::proveInclusion` — bit 0
    means "I'm the left child; sibling is on my right."
    """
    if index < 0 or index >= len(tree.levels[0]):
        raise IndexError(f"leaf index {index} out of range")
    path: list[int] = []
    siblings: list[int] = []
    idx = index
    for d in range(tree.depth):
        is_left = idx % 2 == 0
        sib_idx = idx + 1 if is_left else idx - 1
        path.append(0 if is_left else 1)
        siblings.append(tree.levels[d][sib_idx])
        idx >>= 1
    return InclusionProof(path_indices=path, siblings=siblings)


def yield_leaf(market_id: int, apy_bps: int) -> int:
    """Single yield-oracle leaf: Poseidon(market_id, apy_bps)."""
    return poseidon_hash([market_id, apy_bps])


def allow_leaf(market_id: int) -> int:
    """Single allowlist leaf: Poseidon(market_id)."""
    return poseidon_hash([market_id])


def yield_pad() -> int:
    """Yield-tree pad leaf — Poseidon([0, 0])."""
    return poseidon_hash([0, 0])


def allow_pad() -> int:
    """Allowlist-tree pad leaf — Poseidon([0])."""
    return poseidon_hash([0])


def build_yield_tree(snapshots: list[tuple[int, int]], depth: int = 6) -> MerkleTree:
    """Build the yield-oracle Merkle tree.

    `snapshots` is a list of `(market_id, apy_bps)` pairs. Right-padded
    with `yield_pad()` until length is `2**depth`.
    """
    expected = 1 << depth
    if len(snapshots) > expected:
        raise ValueError(f"too many yield leaves: {len(snapshots)} > {expected}")
    leaves = [yield_leaf(m, a) for m, a in snapshots]
    pad = yield_pad()
    while len(leaves) < expected:
        leaves.append(pad)
    return build_poseidon_tree(leaves, depth)


def build_allowlist_tree(market_ids: list[int], depth: int = 4) -> MerkleTree:
    """Build the markets-allowlist Merkle tree.

    `market_ids` is a list of allowlisted ids. Right-padded with
    `allow_pad()` until length is `2**depth`.
    """
    expected = 1 << depth
    if len(market_ids) > expected:
        raise ValueError(f"too many allowlist leaves: {len(market_ids)} > {expected}")
    leaves = [allow_leaf(m) for m in market_ids]
    pad = allow_pad()
    while len(leaves) < expected:
        leaves.append(pad)
    return build_poseidon_tree(leaves, depth)
