"""Build the witness payload `mean_reversion_v1.circom` expects.

The circuit's public-input layout is identical to `momentum_v1` (14 PIs)
so `StrategyVault.PI_*` indices and the verifier adapter's
`_PUBLIC_INPUT_COUNT = 14` are reused unchanged. The witness shape
mirrors `circuits/scripts/gen-fixture-mr.js`:

  Public:
    trade_hash, declared_class, strategy_vault, params_hash,
    allocator_address, asset_in_idx, asset_out_idx, amount_in,
    min_amount_out, trade_direction, nonce, block_window_start,
    block_window_end, oracle_root.
  Witness:
    max_position_size, max_slippage_bps, signal_threshold (= n_sigma_x100),
    stop_loss_price, price_observations[16], is_long_entry, is_short_entry,
    is_exit, is_signal_flip, is_stop_loss.

`oracle_root`, `trade_hash`, and `params_hash` are computed locally
through `helios.poseidon` (pure-Python BN254 Poseidon, bit-exact against
circomlibjs) so the prover service receives a complete witness and does
not need to do any server-side fixup.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from helios.poseidon import address_to_field, poseidon_chain, poseidon_hash
from helios.types import Direction, TradeIntent

UNIVERSE_SIZE = 8
PRICE_OBSERVATIONS = 16


@dataclass(frozen=True, slots=True)
class WitnessRequest:
    """Prover-ready payload. `inputs` is the JSON sent to
    `services/prover` `POST /prove`; `params_hash` and `oracle_root` are
    surfaced as bytes32 so the runtime can post the same values to
    `StrategyRegistry.commitInitialParamsHash` and check
    `OraclePriceAnchor.isKnownRoot` before submitting the trade.
    """

    strategy_class: str
    inputs: dict[str, Any]
    params_hash: bytes
    oracle_root: bytes
    trade_hash: bytes


def build_mean_reversion_witness(
    *,
    intent: TradeIntent,
    asset_to_universe_idx: dict[str, int],
    asset_universe_addresses: list[str],
    price_observations_e18: list[int],
    declared_class_field: int,
    strategy_vault_address: str,
    allocator_address: str,
    nonce: int,
    block_window_start: int,
    block_window_end: int,
    max_position_size_e18: int,
    max_slippage_bps: int,
    n_sigma_x100: int,
    stop_loss_price_e18: int,
    is_signal_flip: bool,
    is_stop_loss: bool,
    asset_decimals: dict[str, int] | None = None,
    base_asset_balance_raw: int | None = None,
) -> WitnessRequest:
    """Pure helper — no I/O. Tests construct the same payload to assert
    on shape + invariants.

    `base_asset_balance_raw` is the integer balance the vault holds of
    the trade's `asset_in`. When provided, `amount_in` is clamped to it
    so the on-chain `safeTransferFrom` cannot revert on a float-roundtrip
    drift inside `_resolve_amount_in` (intent.amount_in_usd → float →
    int can overshoot the actual vault balance by a few thousand wei
    at ~4.5e19 — float64 ulp territory; `StrategyVault` then surfaces
    that revert as `TradeCallFailed(1)`)."""
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
        raise ValueError("block window > 100 — circuit constraint 5")

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
    if is_signal_flip and is_stop_loss:
        # Circuit constraint 6: is_exit === is_signal_flip + is_stop_loss
        # (so they are mutually exclusive when is_exit == 1).
        raise ValueError("signal_flip and stop_loss cannot both be set")

    asset_in_idx = asset_to_universe_idx[intent.asset_in]
    asset_out_idx = asset_to_universe_idx[intent.asset_out]
    amount_in_native = _resolve_amount_in(intent, padded[-1], asset_decimals)
    if base_asset_balance_raw is not None and amount_in_native > base_asset_balance_raw:
        amount_in_native = base_asset_balance_raw

    # Phase-6 cross-decimal slippage: convert amount_in to expected
    # amount_out at the current oracle price, then apply slippage in
    # asset_out native units. The circuit pins `pow10_asset_in/out` to
    # the live `IERC20.decimals()` via StrategyVault, so the operator
    # can't lie about the conversion factor.
    pow10_in = 10 ** (asset_decimals or {}).get(intent.asset_in, 18)
    pow10_out = 10 ** (asset_decimals or {}).get(intent.asset_out, 18)
    expected_amount_out, min_amount_out_native = _min_amount_out_cross_decimal(
        amount_in=amount_in_native,
        last_price_e18=padded[-1],
        pow10_in=pow10_in,
        pow10_out=pow10_out,
        is_long_entry=bool(is_long_entry),
        max_slippage_bps=intent.max_slippage_bps,
    )

    strategy_vault_field = address_to_field(strategy_vault_address)
    allocator_field = address_to_field(allocator_address)

    # `signal_threshold` is the params slot we're storing n_sigma_x100 in
    # — the `params_hash` Poseidon position is shared with momentum's
    # signal_threshold_bps so the circuit indexing stays uniform.
    params_hash_field = poseidon_hash(
        [max_position_size_e18, max_slippage_bps, n_sigma_x100, stop_loss_price_e18]
    )
    oracle_root_field = poseidon_chain(padded)
    trade_hash_field = poseidon_hash(
        [
            strategy_vault_field,
            declared_class_field,
            params_hash_field,
            allocator_field,
            asset_in_idx,
            asset_out_idx,
            amount_in_native,
            min_amount_out_native,
            direction,
            nonce,
        ]
    )

    inputs: dict[str, Any] = {
        "trade_hash": str(trade_hash_field),
        "declared_class": str(declared_class_field),
        "strategy_vault": str(strategy_vault_field),
        "params_hash": str(params_hash_field),
        "allocator_address": str(allocator_field),
        "asset_in_idx": str(asset_in_idx),
        "asset_out_idx": str(asset_out_idx),
        "amount_in": str(amount_in_native),
        "min_amount_out": str(min_amount_out_native),
        "trade_direction": str(direction),
        "nonce": str(nonce),
        "block_window_start": str(block_window_start),
        "block_window_end": str(block_window_end),
        "oracle_root": str(oracle_root_field),
        # Phase-6 cross-decimal slippage public inputs (positions 14+15).
        "pow10_asset_in": str(pow10_in),
        "pow10_asset_out": str(pow10_out),
        # Witness — operator-private
        "max_position_size": str(max_position_size_e18),
        "max_slippage_bps": str(max_slippage_bps),
        "signal_threshold": str(n_sigma_x100),
        "stop_loss_price": str(stop_loss_price_e18),
        "price_observations": [str(p) for p in padded],
        "is_long_entry": str(is_long_entry),
        "is_short_entry": str(is_short_entry),
        "is_exit": str(is_exit),
        "is_signal_flip": str(int(is_signal_flip)),
        "is_stop_loss": str(int(is_stop_loss)),
        "expected_amount_out": str(expected_amount_out),
    }
    return WitnessRequest(
        strategy_class="mean_reversion_v1",
        inputs=inputs,
        params_hash=params_hash_field.to_bytes(32, "big"),
        oracle_root=oracle_root_field.to_bytes(32, "big"),
        trade_hash=trade_hash_field.to_bytes(32, "big"),
    )


def _resolve_amount_in(
    intent: TradeIntent,
    last_price_e18: int,
    asset_decimals: dict[str, int] | None,
) -> int:
    """Translate a TradeIntent's amount into the integer the circuit
    consumes as `amount_in` and the on-chain swap consumes as
    `amountIn`. Identical semantics to `momentum_v1.witness._resolve_amount_in`
    — see that docstring for the multi-decimal vs legacy modes.
    """
    asset_in = intent.asset_in
    dec = (asset_decimals or {}).get(asset_in)

    if intent.amount_in_usd is not None:
        if dec is None:
            # Legacy Phase-1 same-unit mode (no asset_decimals): USD*1e18.
            return int(intent.amount_in_usd * 10**18)
        usd_scaled = int(intent.amount_in_usd * 10**dec)
        if asset_in == "USDC":
            # USDC is the USD-pegged base (1 USDC ≈ $1 — the convention
            # used across this strategy and asset_universe[0]); the USD
            # notional is already the token amount in its decimals.
            return usd_scaled
        # Priced asset_in (e.g. a sell of WETH/WBTC): convert the USD
        # notional to asset_in units at asset_in's USD price
        # (`last_price_e18`). Without this a $X intent is mis-encoded as
        # X whole tokens — orders of magnitude oversized and unfundable
        # (the swap's safeTransferFrom of an asset the vault doesn't hold
        # at that size reverts as TradeCallFailed(1)).
        if last_price_e18 <= 0:
            raise ValueError("amount_in_usd for a priced asset_in needs last_price_e18 > 0")
        return usd_scaled * 10**18 // last_price_e18

    if intent.amount_in_asset is not None:
        if dec is not None:
            return int(intent.amount_in_asset * 10**dec)
        return int(intent.amount_in_asset * last_price_e18)

    raise ValueError("intent must carry amount_in_usd or amount_in_asset")


def _min_amount_out_cross_decimal(
    *,
    amount_in: int,
    last_price_e18: int,
    pow10_in: int,
    pow10_out: int,
    is_long_entry: bool,
    max_slippage_bps: int,
) -> tuple[int, int]:
    """Returns (expected_amount_out, min_amount_out) — both in asset_out
    native units.

    Mirrors `mean_reversion_v1.circom` Constraints 2a/2b/2c:

      LONG  (USDC → non-USDC asset):
        expected * pow10_in * price = floor(amount_in * pow10_out * 1e18)
      SHORT/EXIT (non-USDC asset → USDC):
        expected * pow10_in * 1e18  = floor(amount_in * pow10_out * price)

    `expected` is pinned to the exact floor by Constraints 2a/2b.
    `min_amount_out` is `ceil(expected * (10000 - slippage_bps) / 10000)`
    — the smallest value that still satisfies the circuit's slippage
    inequality.
    """
    ONE_E18 = 10**18
    if is_long_entry:
        # USDC → asset
        num = pow10_out * ONE_E18
        denom = pow10_in * last_price_e18
    else:
        # asset → USDC (SHORT or EXIT)
        num = pow10_out * last_price_e18
        denom = pow10_in * ONE_E18
    if denom == 0:
        raise ValueError("cross-decimal conversion denominator is zero")
    expected = (amount_in * num) // denom
    slip_term = expected * (10_000 - max_slippage_bps)
    min_amount_out = (slip_term + 9_999) // 10_000
    return expected, min_amount_out
