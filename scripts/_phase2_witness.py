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
from oracle.poseidon import poseidon_chain, poseidon_hash  # noqa: E402

from helios_contracts_abi.class_ids import class_id_as_field  # noqa: E402

PRICE_OBSERVATIONS = 16


@dataclass(frozen=True, slots=True)
class MomentumWitness:
    """Result of `build_momentum_witness`.

    `inputs` is the full prover payload (POST /prove `witnessInputs`).
    `params_hash` is the bytes32 to commit via
    `StrategyRegistry.commitInitialParamsHash` before this proof can land
    — it equals `Poseidon([max_position_size, max_slippage_bps,
    signal_threshold, stop_loss_price])` and the circuit re-derives it
    from the private witnesses.
    """

    inputs: dict[str, Any]
    params_hash: bytes


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
        raise ValueError(
            f"price_observations_e18 must be exactly {PRICE_OBSERVATIONS} bars"
        )
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
    )


__all__ = ["MomentumWitness", "PRICE_OBSERVATIONS", "build_momentum_witness"]
