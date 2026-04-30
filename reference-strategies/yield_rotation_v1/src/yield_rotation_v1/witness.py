"""Build the witness payload yield_rotation_v1.circom expects.

YR is structurally distinct from the directional classes — 9 PIs, no
asset indices, no params_hash. The witness ships full Merkle inclusion
proofs (yield depth 6, allowlist depth 4) which the strategy operator
builds client-side using `merkle.py`. `trade_hash` is also computed
client-side here (Poseidon over 11 fields) — unlike momentum/MR, the
YR fixture script computes the trade hash before calling
`groth16.fullProve`, so the witness is fully populated by the time it
reaches the prover service.

Mirrors `circuits/scripts/gen-fixture-yr.js` line for line — vector
parity is asserted in `tests/test_witness.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from oracle.poseidon import poseidon_hash

from yield_rotation_v1.merkle import (
    MerkleTree,
    allow_leaf,
    build_allowlist_tree,
    build_yield_tree,
    inclusion_proof,
)
from yield_rotation_v1.types import RotationIntent, YieldTick

YIELD_TREE_DEPTH = 6  # 64 markets per yield-oracle snapshot
ALLOW_TREE_DEPTH = 4  # 16 markets in registry allowlist


@dataclass(frozen=True, slots=True)
class WitnessRequest:
    """Raw payload sent to the prover. For yield_rotation_v1 every
    Poseidon hash is computed client-side, so `pending_poseidon` is
    empty (unlike momentum/MR where the prover fills `oracle_root` and
    `trade_hash`)."""

    strategy_class: str
    inputs: dict[str, Any]
    trade_hash: int  # surfaced for the Foundry-fixture round-trip test
    yield_root: int
    allowlist_root: int
    pending_poseidon: tuple[str, ...] = field(default=())


def build_yield_rotation_witness(
    *,
    intent: RotationIntent,
    yield_snapshots: list[YieldTick],
    allowlisted_markets: list[int],
    declared_class_field: int,
    allocator_address: str,
    nonce: int,
    block_window_end: int,
    signal_threshold_bps: int,
    bridging_cost_bps: int,
) -> WitnessRequest:
    """Pure helper — no I/O. `yield_snapshots` is the operator's
    reconstructed view of the yield Merkle tree (one entry per market in
    the snapshot window); `allowlisted_markets` is the canonical
    registry allowlist (operator must mirror it locally so proofs key
    against the same root the on-chain side accepts)."""
    if intent.m_from == intent.m_to:
        raise ValueError("rotation must change markets")
    if intent.amount_in_usd <= 0:
        raise ValueError("amount must be positive")
    if intent.m_from not in allowlisted_markets:
        raise ValueError(f"m_from {intent.m_from} not in allowlist")
    if intent.m_to not in allowlisted_markets:
        raise ValueError(f"m_to {intent.m_to} not in allowlist")
    if not yield_snapshots:
        raise ValueError("yield_snapshots required")

    market_to_idx = {snap.market_id: i for i, snap in enumerate(yield_snapshots)}
    if intent.m_from not in market_to_idx:
        raise ValueError(f"yield snapshot missing for m_from={intent.m_from}")
    if intent.m_to not in market_to_idx:
        raise ValueError(f"yield snapshot missing for m_to={intent.m_to}")

    # Yield tree leaves use plain bps (apy_bps_e6 // 1_000_000) — must
    # match the circuit's 16-bit range checks AND the on-chain anchor's
    # canonical leaf encoding.
    yield_pairs = [(s.market_id, _e6_to_bps(s.apy_bps_e6)) for s in yield_snapshots]
    yield_tree = build_yield_tree(yield_pairs, depth=YIELD_TREE_DEPTH)

    allowlist_tree = build_allowlist_tree(list(allowlisted_markets), depth=ALLOW_TREE_DEPTH)

    yp_from = inclusion_proof(yield_tree, market_to_idx[intent.m_from])
    yp_to = inclusion_proof(yield_tree, market_to_idx[intent.m_to])

    allow_idx_from = allowlisted_markets.index(intent.m_from)
    allow_idx_to = allowlisted_markets.index(intent.m_to)
    ap_from = inclusion_proof(allowlist_tree, allow_idx_from)
    ap_to = inclusion_proof(allowlist_tree, allow_idx_to)

    # APY values bound to the leaves we proved inclusion of.
    apy_from = _e6_to_bps(yield_snapshots[market_to_idx[intent.m_from]].apy_bps_e6)
    apy_to = _e6_to_bps(yield_snapshots[market_to_idx[intent.m_to]].apy_bps_e6)
    if apy_to - apy_from < signal_threshold_bps + bridging_cost_bps:
        raise ValueError("APY differential below threshold + bridging cost")

    amount_rotating_e18 = int(intent.amount_in_usd * 10**18)
    allocator_field = _address_to_field(allocator_address)
    yield_root = yield_tree.root
    allowlist_root = allowlist_tree.root

    # trade_hash binds the public + private operator-set + registry-set
    # fields into a single Poseidon. The on-chain side expects this
    # exact ordering (see Helios.md §9.4 + circuit constraint 8).
    trade_hash = poseidon_hash(
        [
            declared_class_field,
            intent.m_from,
            intent.m_to,
            amount_rotating_e18,
            yield_root,
            allocator_field,
            nonce,
            block_window_end,
            signal_threshold_bps,
            bridging_cost_bps,
            allowlist_root,
        ]
    )

    inputs: dict[str, Any] = {
        # Public (9)
        "trade_hash": str(trade_hash),
        "declared_class": str(declared_class_field),
        "m_from": str(intent.m_from),
        "m_to": str(intent.m_to),
        "amount_rotating": str(amount_rotating_e18),
        "yield_oracle_root": str(yield_root),
        "allocator_address": str(allocator_field),
        "nonce": str(nonce),
        "block_window_end": str(block_window_end),
        # Private witness
        "apy_from": str(apy_from),
        "apy_to": str(apy_to),
        "signal_threshold": str(signal_threshold_bps),
        "bridging_cost": str(bridging_cost_bps),
        "markets_allowlist_root": str(allowlist_root),
        "yield_path_indices_from": [str(i) for i in yp_from.path_indices],
        "yield_siblings_from": [str(s) for s in yp_from.siblings],
        "yield_path_indices_to": [str(i) for i in yp_to.path_indices],
        "yield_siblings_to": [str(s) for s in yp_to.siblings],
        "allow_path_indices_from": [str(i) for i in ap_from.path_indices],
        "allow_siblings_from": [str(s) for s in ap_from.siblings],
        "allow_path_indices_to": [str(i) for i in ap_to.path_indices],
        "allow_siblings_to": [str(s) for s in ap_to.siblings],
    }
    return WitnessRequest(
        strategy_class="yield_rotation_v1",
        inputs=inputs,
        trade_hash=trade_hash,
        yield_root=yield_root,
        allowlist_root=allowlist_root,
    )


def reconstruct_yield_root(snapshots: list[YieldTick]) -> int:
    """Convenience helper for callers that just want to commit / verify a
    yield root without building a full witness (e.g. the runtime's
    health endpoint)."""
    pairs = [(s.market_id, _e6_to_bps(s.apy_bps_e6)) for s in snapshots]
    return build_yield_tree(pairs, depth=YIELD_TREE_DEPTH).root


def reconstruct_allowlist_root(market_ids: list[int]) -> int:
    return build_allowlist_tree(list(market_ids), depth=ALLOW_TREE_DEPTH).root


def _allow_leaf_for(market_id: int) -> int:
    return allow_leaf(market_id)


def _e6_to_bps(apy_bps_e6: int) -> int:
    return apy_bps_e6 // 1_000_000


def _address_to_field(addr_or_symbol: str) -> int:
    s = addr_or_symbol
    if s.startswith("0x") or s.startswith("0X"):
        return int(s, 16)
    raw = s.encode("latin-1")
    return int.from_bytes(raw, "big")


# Re-export tree handle for tests.
__all__ = [
    "ALLOW_TREE_DEPTH",
    "YIELD_TREE_DEPTH",
    "MerkleTree",
    "WitnessRequest",
    "build_yield_rotation_witness",
    "reconstruct_allowlist_root",
    "reconstruct_yield_root",
]
