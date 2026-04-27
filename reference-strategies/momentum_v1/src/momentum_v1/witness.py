"""Build the witness payload momentum_v1.circom expects.

The circuit expects 16 price observations Poseidon-chained to an
`oracle_root`, and a `trade_hash` Poseidon over the public trade
fields. Computing Poseidon in pure Python would mean adding a
BN254-compatible implementation to the dep tree — instead, the
prover service (Node.js + circomlibjs) completes both fields
server-side. We submit the rest of the witness ready-formed.

Public-input ordering MUST match `StrategyVault.PI_*` indices:
  0 asset_in, 1 asset_out, 2 amount_in, 3 min_amount_out,
  4 direction, 5 block_window_start, 6 block_window_end, 7 trade_hash.
The prover-side wrapper is responsible for emitting `publicSignals`
in this order so `TradeAttestationVerifier.verify` succeeds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from helios.types import Direction, TradeIntent

UNIVERSE_SIZE = 8
PRICE_OBSERVATIONS = 16


@dataclass(frozen=True, slots=True)
class WitnessRequest:
    """Raw payload sent to the prover. The prover completes
    `oracle_root` + `trade_hash` via circomlibjs Poseidon."""

    strategy_class: str
    inputs: dict[str, Any]
    pending_poseidon: tuple[str, ...] = field(default=("oracle_root", "trade_hash"))


def build_momentum_witness(
    *,
    intent: TradeIntent,
    asset_to_universe_idx: dict[str, int],
    asset_universe_addresses: list[str],
    price_observations_e18: list[int],
    declared_class_field: int,
    allocator_address: str,
    nonce: int,
    block_window_start: int,
    block_window_end: int,
    max_position_size_e18: int,
    max_slippage_bps: int,
    signal_threshold_bps: int,
    position_state_e18: int,
    stop_loss_price_e18: int,
    is_signal_flip: bool,
    is_stop_loss: bool,
) -> WitnessRequest:
    """Pure helper — no I/O. Tests construct the same payload to assert
    on shape + invariants."""
    if len(asset_universe_addresses) != UNIVERSE_SIZE:
        raise ValueError(f"asset_universe must be {UNIVERSE_SIZE} entries")
    if (
        intent.asset_in not in asset_to_universe_idx
        or intent.asset_out not in asset_to_universe_idx
    ):
        raise ValueError("trade asset not in universe")
    if len(price_observations_e18) > PRICE_OBSERVATIONS:
        raise ValueError(f"price_observations must be ≤ {PRICE_OBSERVATIONS} bars")
    if block_window_end - block_window_start > 100:
        raise ValueError("block window > 100 — circuit constraint 6")

    # Pad observations on the left with the oldest bar repeating (the
    # circuit treats every position as a real observation; the chain's
    # stability matters more than a perfectly fresh history).
    padded = [price_observations_e18[0]] * (
        PRICE_OBSERVATIONS - len(price_observations_e18)
    ) + price_observations_e18

    direction = int(intent.direction)
    is_long_entry = 1 if intent.direction == Direction.LONG else 0
    is_short_entry = 1 if intent.direction == Direction.SHORT else 0
    is_exit = 1 if intent.direction == Direction.EXIT else 0
    if is_exit and not (is_signal_flip or is_stop_loss):
        raise ValueError("exit must specify signal_flip OR stop_loss")
    if not is_exit and (is_signal_flip or is_stop_loss):
        raise ValueError("non-exit cannot set signal_flip / stop_loss")

    amount_in_e18 = _resolve_amount_in_e18(intent, padded[-1])
    min_amount_out_e18 = _min_amount_out_e18(amount_in_e18, intent.max_slippage_bps)

    inputs: dict[str, Any] = {
        # Public — circuit + verifier
        "trade_hash": "0",  # filled by prover
        "declared_class": str(declared_class_field),
        "asset_in": str(
            _asset_to_field(asset_universe_addresses[asset_to_universe_idx[intent.asset_in]])
        ),
        "asset_out": str(
            _asset_to_field(asset_universe_addresses[asset_to_universe_idx[intent.asset_out]])
        ),
        "amount_in": str(amount_in_e18),
        "min_amount_out": str(min_amount_out_e18),
        "trade_direction": str(direction),
        "allocator_address": str(_asset_to_field(allocator_address)),
        "nonce": str(nonce),
        "block_window_start": str(block_window_start),
        "block_window_end": str(block_window_end),
        # Witness — operator-private
        "asset_universe": [str(_asset_to_field(a)) for a in asset_universe_addresses],
        "max_position_size": str(max_position_size_e18),
        "max_slippage_bps": str(max_slippage_bps),
        "position_state": str(position_state_e18),
        "signal_threshold": str(signal_threshold_bps),
        "price_observations": [str(p) for p in padded],
        "oracle_root": "0",  # filled by prover
        "is_long_entry": str(is_long_entry),
        "is_short_entry": str(is_short_entry),
        "is_exit": str(is_exit),
        "is_signal_flip": str(int(is_signal_flip)),
        "is_stop_loss": str(int(is_stop_loss)),
        "stop_loss_price": str(stop_loss_price_e18),
    }
    return WitnessRequest(strategy_class="momentum_v1", inputs=inputs)


def _resolve_amount_in_e18(intent: TradeIntent, last_price_e18: int) -> int:
    """Translate a TradeIntent's amount into a uint256 e18 value.

    Phase 1 simplifying assumption: USDC (the base asset) and the
    on-circuit `amount_in` share a single 18-decimal scaling. Real
    USDC has 6 decimals; the on-chain MockSwapRouter normalizes for
    the demo. Hardening lands when we move to real Algebra in Phase 2.
    """
    if intent.amount_in_usd is not None:
        # USDC value in 18-dec.
        return int(intent.amount_in_usd * 10**18)
    if intent.amount_in_asset is not None:
        # Asset quantity × last price → quote-asset notional in 18-dec.
        return int(intent.amount_in_asset * last_price_e18)
    raise ValueError("intent must carry amount_in_usd or amount_in_asset")


def _min_amount_out_e18(amount_in_e18: int, max_slippage_bps: int) -> int:
    return amount_in_e18 * (10_000 - max_slippage_bps) // 10_000


def _asset_to_field(addr_or_symbol: str) -> int:
    """Either a hex address or a short symbol. Hex addresses → uint160 int.
    Short symbols are hashed via Python's `hash(...)` would be unstable
    across processes; instead we treat them as latin-1 bytes interpreted
    as a big-endian integer (deterministic, fits within BN254 for any
    symbol up to ~30 bytes)."""
    s = addr_or_symbol
    if s.startswith("0x") or s.startswith("0X"):
        return int(s, 16)
    raw = s.encode("latin-1")
    return int.from_bytes(raw, "big")
