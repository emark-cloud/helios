"""WS6 PR2 — witness builders for the Phase 2 e2e prover client.

The reference strategy SDK's witness modules currently submit `"0"` for
`oracle_root` / `trade_hash` and rely on a server-side completion that
the prover service does not actually perform. They predate the
Phase 2 cutover from mock to real Groth16 verifiers, so they were
never exercised end-to-end. This module is the missing piece: takes
public + private parameters, computes the Poseidon-bound fields with
the same circomlibjs Poseidon the circuits use, and emits a
prover-ready witness dict.

Imported by `scripts/e2e_scenario_phase2.py`. Eventually the logic
here should graduate into the strategy-sdk so external operators can
use it directly; that's a follow-up to WS6 (the reference strategies
need a broader fix anyway — see the WS6 retro note in TODO.md).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# `oracle.poseidon` already shells out to the canonical circomlibjs Poseidon
# helper kept warm across calls. Importing it from a non-installed path so
# this module works inside `uv run --package helios-sentinel`, which has
# helios-sentinel + its deps but not helios-oracle on the path.
_ORACLE_SRC = Path(__file__).resolve().parent.parent / "services" / "oracle" / "src"
if str(_ORACLE_SRC) not in sys.path:
    sys.path.insert(0, str(_ORACLE_SRC))
from helios_contracts_abi.class_ids import class_id_as_field
from oracle.poseidon import poseidon_chain, poseidon_hash

PRICE_OBSERVATIONS = 16


@dataclass(frozen=True, slots=True)
class MomentumWitness:
    """Result of `build_momentum_witness`.

    `inputs` is the full prover payload (POST /prove `witnessInputs`).
    `params_hash` is the bytes32 to commit via
    `StrategyRegistry.commitInitialParamsHash` before this proof can land
    — it equals `Poseidon([max_position_size, max_slippage_bps,
    signal_threshold, stop_loss_price])` and the circuit re-derives it
    from the private witnesses. `oracle_root` is the bytes32 to commit
    via `OraclePriceAnchor.commit` before this proof can land — PR1a
    binding (`isKnownRoot`) gates execution on it.
    """

    inputs: dict[str, Any]
    params_hash: bytes
    oracle_root: bytes


def build_momentum_witness(
    *,
    strategy_vault: str,
    allocator_vault: str,
    nonce: int,
    block_window_start: int,
    block_window_end: int,
    price_observations_e18: list[int],
    max_position_size: int = 5 * 10**18,
    max_slippage_bps: int = 50,
    signal_threshold_bps: int = 100,
    stop_loss_price: int = 0,
    asset_in_idx: int = 0,
    asset_out_idx: int = 0,
    amount_in: int = 1 * 10**18,
) -> MomentumWitness:
    """Build a long-entry momentum_v1 witness against the deployed vault.

    The defaults track the canonical `circuits/scripts/gen-fixture.js`
    knobs (long entry; threshold 100bps; size cap 5e18; min_amount_out
    derived from slippage). Callers normally only need to supply the
    addresses, nonce, block window, and price series. The price series
    must be 16 monotonically-increasing observations for the long-entry
    rule to fire — `(price_last - price_first) * 10000 >=
    signal_threshold * price_first`.
    """
    if len(price_observations_e18) != PRICE_OBSERVATIONS:
        raise ValueError(f"price_observations_e18 must be exactly {PRICE_OBSERVATIONS} bars")
    if amount_in > max_position_size:
        raise ValueError("amount_in > max_position_size violates circuit constraint 1")

    # Slippage: min_amount_out = amount_in * (1 - slippage). Equality
    # satisfies the slippage check.
    min_amount_out = amount_in * (10_000 - max_slippage_bps) // 10_000

    # Field representations of address-shaped public signals.
    strategy_vault_field = int(strategy_vault, 16)
    allocator_field = int(allocator_vault, 16)
    declared_class_field = class_id_as_field("momentum_v1")

    params_hash = poseidon_hash(
        [max_position_size, max_slippage_bps, signal_threshold_bps, stop_loss_price]
    )

    oracle_root = poseidon_chain(price_observations_e18)

    trade_direction = 1  # long entry
    trade_hash = poseidon_hash(
        [
            strategy_vault_field,
            declared_class_field,
            params_hash,
            allocator_field,
            asset_in_idx,
            asset_out_idx,
            amount_in,
            min_amount_out,
            trade_direction,
            nonce,
        ]
    )

    inputs: dict[str, Any] = {
        # Public — the circuit's `main { public [...] }` block.
        "trade_hash": str(trade_hash),
        "declared_class": str(declared_class_field),
        "strategy_vault": str(strategy_vault_field),
        "params_hash": str(params_hash),
        "allocator_address": str(allocator_field),
        "asset_in_idx": str(asset_in_idx),
        "asset_out_idx": str(asset_out_idx),
        "amount_in": str(amount_in),
        "min_amount_out": str(min_amount_out),
        "trade_direction": str(trade_direction),
        "nonce": str(nonce),
        "block_window_start": str(block_window_start),
        "block_window_end": str(block_window_end),
        "oracle_root": str(oracle_root),
        # Private — operator-declared bounds + per-bar price witnesses.
        "max_position_size": str(max_position_size),
        "max_slippage_bps": str(max_slippage_bps),
        "signal_threshold": str(signal_threshold_bps),
        "stop_loss_price": str(stop_loss_price),
        "price_observations": [str(p) for p in price_observations_e18],
        # One-hot direction selectors. Long entry only, in this builder.
        "is_long_entry": "1",
        "is_short_entry": "0",
        "is_exit": "0",
        "is_signal_flip": "0",
        "is_stop_loss": "0",
    }
    return MomentumWitness(
        inputs=inputs,
        params_hash=params_hash.to_bytes(32, "big"),
        oracle_root=oracle_root.to_bytes(32, "big"),
    )


@dataclass(frozen=True, slots=True)
class MeanReversionWitness:
    """Result of `build_mean_reversion_witness`. Same shape as
    `MomentumWitness` — distinct dataclass for type-clarity at call sites.
    """

    inputs: dict[str, Any]
    params_hash: bytes
    oracle_root: bytes


def build_mean_reversion_witness(
    *,
    strategy_vault: str,
    allocator_vault: str,
    nonce: int,
    block_window_start: int,
    block_window_end: int,
    price_observations: list[int],
    max_position_size: int = 5 * 10**18,
    max_slippage_bps: int = 50,
    n_sigma_x100: int = 200,
    stop_loss_price: int = 0,
    asset_in_idx: int = 0,
    asset_out_idx: int = 0,
    amount_in: int = 1 * 10**18,
) -> MeanReversionWitness:
    """Build a long-entry mean_reversion_v1 witness against the deployed
    vault.

    The defaults track `circuits/scripts/gen-fixture-mr.js`: 16-bar
    series with 15 bars at one price and the last at a deep dip. Long
    entry triggers when `160_000 * dev_last_sq >= n_sigma_x100² *
    sum_sq_devs`, with the additional sign constraint that the last
    bar lies below the 16-bar mean (`sum_total >= 16 * price_last`).
    `n_sigma_x100` slot in `params_hash` is what momentum calls
    `signal_threshold` — same field position, different semantics
    (e.g. `200` ⇒ 2.00σ).
    """
    if len(price_observations) != PRICE_OBSERVATIONS:
        raise ValueError(f"price_observations must be exactly {PRICE_OBSERVATIONS} bars")
    if amount_in > max_position_size:
        raise ValueError("amount_in > max_position_size violates circuit constraint 1")

    # Last bar must be strictly below the 16-bar mean for a long entry.
    sum_total = sum(price_observations)
    if 16 * price_observations[15] >= sum_total:
        raise ValueError(
            "long entry requires price_last below the 16-bar mean "
            "(sum_total > 16 * price_observations[15])"
        )

    min_amount_out = amount_in * (10_000 - max_slippage_bps) // 10_000

    strategy_vault_field = int(strategy_vault, 16)
    allocator_field = int(allocator_vault, 16)
    declared_class_field = class_id_as_field("mean_reversion_v1")

    # `signal_threshold` is the params slot we're storing n_sigma_x100 in.
    params_hash = poseidon_hash(
        [max_position_size, max_slippage_bps, n_sigma_x100, stop_loss_price]
    )

    oracle_root = poseidon_chain(price_observations)

    trade_direction = 1  # long entry
    trade_hash = poseidon_hash(
        [
            strategy_vault_field,
            declared_class_field,
            params_hash,
            allocator_field,
            asset_in_idx,
            asset_out_idx,
            amount_in,
            min_amount_out,
            trade_direction,
            nonce,
        ]
    )

    inputs: dict[str, Any] = {
        "trade_hash": str(trade_hash),
        "declared_class": str(declared_class_field),
        "strategy_vault": str(strategy_vault_field),
        "params_hash": str(params_hash),
        "allocator_address": str(allocator_field),
        "asset_in_idx": str(asset_in_idx),
        "asset_out_idx": str(asset_out_idx),
        "amount_in": str(amount_in),
        "min_amount_out": str(min_amount_out),
        "trade_direction": str(trade_direction),
        "nonce": str(nonce),
        "block_window_start": str(block_window_start),
        "block_window_end": str(block_window_end),
        "oracle_root": str(oracle_root),
        "max_position_size": str(max_position_size),
        "max_slippage_bps": str(max_slippage_bps),
        "signal_threshold": str(n_sigma_x100),  # field name fixed by circuit
        "stop_loss_price": str(stop_loss_price),
        "price_observations": [str(p) for p in price_observations],
        "is_long_entry": "1",
        "is_short_entry": "0",
        "is_exit": "0",
        "is_signal_flip": "0",
        "is_stop_loss": "0",
    }
    return MeanReversionWitness(
        inputs=inputs,
        params_hash=params_hash.to_bytes(32, "big"),
        oracle_root=oracle_root.to_bytes(32, "big"),
    )


# ── yield_rotation_v1 ────────────────────────────────────────────

YIELD_DEPTH = 6  # 64 markets per yield-oracle snapshot
ALLOW_DEPTH = 4  # 16 markets in the registry allowlist


@dataclass(frozen=True, slots=True)
class YieldRotationWitness:
    """Result of `build_yield_rotation_witness`. Mirrors `MomentumWitness`:
    `params_hash` is the bytes32 to commit via
    `StrategyRegistry.commitInitialParamsHash` before the proof can land —
    it equals `Poseidon(signal_threshold, bridging_cost)` and the circuit
    re-derives it from the private witnesses. `markets_allowlist_root` is
    the bytes32 to set via `StrategyRegistry.setMarketAllowlistRoot` for
    the YR class so the on-chain `AllowlistRootMismatch` check passes."""

    inputs: dict[str, Any]
    yield_oracle_root: int
    markets_allowlist_root: int
    params_hash: bytes


def _build_poseidon_tree(leaves: list[int], depth: int) -> tuple[int, list[list[int]]]:
    """Poseidon Merkle tree with internal nodes = `Poseidon([left, right])`.
    Returns (root, levels). levels[0] is the leaf row; levels[depth] is the
    root row. Mirrors `circuits/scripts/gen-fixture-yr.js::buildTree`."""
    expected = 1 << depth
    if len(leaves) != expected:
        raise ValueError(f"expected {expected} leaves, got {len(leaves)}")
    levels: list[list[int]] = [list(leaves)]
    for _ in range(depth):
        cur = levels[-1]
        nxt = [poseidon_hash([cur[i], cur[i + 1]]) for i in range(0, len(cur), 2)]
        levels.append(nxt)
    return levels[depth][0], levels


def _merkle_inclusion(
    levels: list[list[int]], index: int, depth: int
) -> tuple[list[str], list[str]]:
    """Inclusion proof for a leaf at `index`. Mirrors `proveInclusion`
    in gen-fixture-yr.js: `path_indices[i] == "0"` means the sibling
    sits to the right at level i; "1" means it sits to the left."""
    path_indices: list[str] = []
    siblings: list[str] = []
    idx = index
    for d in range(depth):
        is_left = idx % 2 == 0
        sib_idx = idx + 1 if is_left else idx - 1
        path_indices.append("0" if is_left else "1")
        siblings.append(str(levels[d][sib_idx]))
        idx >>= 1
    return path_indices, siblings


# Canonical 4-market test cosmos. Values mirror `gen-fixture-yr.js` so
# the witness shape is identical to the verifier-only fixture, but with
# a per-call allocator_address and nonce for the e2e.
_MARKETS: dict[str, int] = {
    "AAVE_USDC": 1,
    "COMPOUND_USDC": 2,
    "AAVE_USDT": 3,
    "COMPOUND_USDT": 4,
}
_APY_BPS: dict[str, int] = {
    "AAVE_USDC": 420,
    "COMPOUND_USDC": 550,
    "AAVE_USDT": 380,
    "COMPOUND_USDT": 500,
}
# Indices in the leaf rows (insertion order). Used to derive Merkle paths.
_MARKET_ORDER: list[str] = ["AAVE_USDC", "COMPOUND_USDC", "AAVE_USDT", "COMPOUND_USDT"]


def build_yield_rotation_witness(
    *,
    strategy_vault: str,
    allocator_vault: str,
    nonce: int,
    block_window_end: int,
    block_window_start: int,
    from_market: str = "AAVE_USDC",
    to_market: str = "COMPOUND_USDC",
    amount_rotating: int = 1 * 10**18,
    signal_threshold_bps: int = 80,
    bridging_cost_bps: int = 30,
) -> YieldRotationWitness:
    """Build a yield_rotation_v1 witness for a rotation between two of
    the four canonical markets. Defaults track `gen-fixture-yr.js`:
    AAVE_USDC (420 bps) → COMPOUND_USDC (550 bps), threshold 80,
    bridging 30 ⇒ differential 130 ≥ 110 (passes Constraint 6)."""
    if from_market not in _MARKETS or to_market not in _MARKETS:
        raise ValueError(f"unknown market in {(from_market, to_market)!r}")
    if from_market == to_market:
        raise ValueError("from_market == to_market violates Constraint 5")

    # Leaves are pre-Poseidon-hashed: yield leaf = Poseidon(market_id, apy);
    # allowlist leaf = Poseidon(market_id). Pad both trees up to 2^depth.
    yield_leaves = [poseidon_hash([_MARKETS[m], _APY_BPS[m]]) for m in _MARKET_ORDER]
    yield_pad = poseidon_hash([0, 0])
    while len(yield_leaves) < (1 << YIELD_DEPTH):
        yield_leaves.append(yield_pad)
    yield_root, yield_levels = _build_poseidon_tree(yield_leaves, YIELD_DEPTH)

    allow_leaves = [poseidon_hash([_MARKETS[m]]) for m in _MARKET_ORDER]
    allow_pad = poseidon_hash([0])
    while len(allow_leaves) < (1 << ALLOW_DEPTH):
        allow_leaves.append(allow_pad)
    allow_root, allow_levels = _build_poseidon_tree(allow_leaves, ALLOW_DEPTH)

    from_idx = _MARKET_ORDER.index(from_market)
    to_idx = _MARKET_ORDER.index(to_market)

    yp_from_indices, yp_from_siblings = _merkle_inclusion(yield_levels, from_idx, YIELD_DEPTH)
    yp_to_indices, yp_to_siblings = _merkle_inclusion(yield_levels, to_idx, YIELD_DEPTH)
    ap_from_indices, ap_from_siblings = _merkle_inclusion(allow_levels, from_idx, ALLOW_DEPTH)
    ap_to_indices, ap_to_siblings = _merkle_inclusion(allow_levels, to_idx, ALLOW_DEPTH)

    declared_class_field = class_id_as_field("yield_rotation_v1")
    allocator_field = int(allocator_vault, 16)
    strategy_vault_field = int(strategy_vault, 16)
    m_from_field = _MARKETS[from_market]
    m_to_field = _MARKETS[to_market]

    # PR2: signal_threshold + bridging_cost stay private, but their
    # commitment (params_hash = Poseidon(threshold, bridging)) is now a
    # public input — the vault checks it against `_activeParamsHash()`.
    params_hash_int = poseidon_hash([signal_threshold_bps, bridging_cost_bps])

    # 12-element trade_hash. Field order MUST match
    # circuits/yield_rotation_v1.circom Constraint 9.
    trade_hash = poseidon_hash(
        [
            declared_class_field,
            strategy_vault_field,
            params_hash_int,
            allow_root,
            m_from_field,
            m_to_field,
            amount_rotating,
            yield_root,
            allocator_field,
            nonce,
            block_window_end,
            block_window_start,
        ]
    )

    inputs: dict[str, Any] = {
        # Public — circuit's `main { public [...] }`.
        "trade_hash": str(trade_hash),
        "declared_class": str(declared_class_field),
        "strategy_vault": str(strategy_vault_field),
        "params_hash": str(params_hash_int),
        "markets_allowlist_root": str(allow_root),
        "m_from": str(m_from_field),
        "m_to": str(m_to_field),
        "amount_rotating": str(amount_rotating),
        "yield_oracle_root": str(yield_root),
        "allocator_address": str(allocator_field),
        "nonce": str(nonce),
        "block_window_end": str(block_window_end),
        "block_window_start": str(block_window_start),
        # Private witness.
        "apy_from": str(_APY_BPS[from_market]),
        "apy_to": str(_APY_BPS[to_market]),
        "signal_threshold": str(signal_threshold_bps),
        "bridging_cost": str(bridging_cost_bps),
        "yield_path_indices_from": yp_from_indices,
        "yield_siblings_from": yp_from_siblings,
        "yield_path_indices_to": yp_to_indices,
        "yield_siblings_to": yp_to_siblings,
        "allow_path_indices_from": ap_from_indices,
        "allow_siblings_from": ap_from_siblings,
        "allow_path_indices_to": ap_to_indices,
        "allow_siblings_to": ap_to_siblings,
    }
    return YieldRotationWitness(
        inputs=inputs,
        yield_oracle_root=yield_root,
        markets_allowlist_root=allow_root,
        params_hash=params_hash_int.to_bytes(32, "big"),
    )


__all__ = [
    "ALLOW_DEPTH",
    "PRICE_OBSERVATIONS",
    "YIELD_DEPTH",
    "MeanReversionWitness",
    "MomentumWitness",
    "YieldRotationWitness",
    "build_mean_reversion_witness",
    "build_momentum_witness",
    "build_yield_rotation_witness",
]
