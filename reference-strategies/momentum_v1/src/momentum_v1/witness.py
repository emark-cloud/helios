"""Build the witness payload `momentum_v1.circom` expects.

The circuit takes 16 price observations Poseidon-chained to an
`oracle_root`, plus a `params_hash` over the operator's declared bounds
and a `trade_hash` Poseidon over the public trade fields. All three
Poseidon-bound values are computed locally via `helios.poseidon` (a
pure-Python BN254 Poseidon, bit-exact against circomlibjs) so the
prover service can submit the witness directly to snarkjs without any
server-side fixup.

Public-input ordering MUST match `StrategyVault.PI_*` indices and the
`{ public [...] }` block in `momentum_v1.circom`:

    0  trade_hash             8  min_amount_out
    1  declared_class         9  trade_direction
    2  strategy_vault         10 nonce
    3  params_hash            11 block_window_start
    4  allocator_address      12 block_window_end
    5  asset_in_idx           13 oracle_root
    6  asset_out_idx
    7  amount_in
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


def build_momentum_witness(
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
    signal_threshold_bps: int,
    stop_loss_price_e18: int,
    is_signal_flip: bool,
    is_stop_loss: bool,
    was_long: bool = True,
    asset_decimals: dict[str, int] | None = None,
    base_asset_balance_raw: int | None = None,
) -> WitnessRequest:
    """Pure helper — no I/O. Tests construct the same payload to assert
    on shape + invariants.

    `base_asset_balance_raw` clamps `amount_in` to the vault's actual
    on-chain integer balance. See `mean_reversion_v1.witness` docstring
    for the float-roundtrip drift this guards against (TradeCallFailed(1)
    from `StrategyVault` when `safeTransferFrom` reverts on a few-K-wei
    overshoot)."""
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
    # circuit treats every position as a real observation; chain
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

    asset_in_idx = asset_to_universe_idx[intent.asset_in]
    asset_out_idx = asset_to_universe_idx[intent.asset_out]
    amount_in_native = _resolve_amount_in(intent, padded[-1], asset_decimals)
    if base_asset_balance_raw is not None and amount_in_native > base_asset_balance_raw:
        amount_in_native = base_asset_balance_raw

    # Phase-6 cross-decimal slippage: convert amount_in to expected
    # amount_out at the current oracle price, then apply slippage in
    # asset_out native units. StrategyVault pins `pow10_asset_in/out`
    # to `IERC20.decimals()` so the operator can't lie about scaling.
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

    # Poseidon completions — match the `ph(...)` invocations in
    # `circuits/scripts/gen-fixture.js` and the in-circuit checks in
    # `momentum_v1.circom` (Constraint 0 for params_hash, the chain
    # build for oracle_root, the trade-binding hash for trade_hash).
    params_hash_field = poseidon_hash(
        [max_position_size_e18, max_slippage_bps, signal_threshold_bps, stop_loss_price_e18]
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
        # Public — circuit + verifier
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
        "signal_threshold": str(signal_threshold_bps),
        "stop_loss_price": str(stop_loss_price_e18),
        "price_observations": [str(p) for p in padded],
        "is_long_entry": str(is_long_entry),
        "is_short_entry": str(is_short_entry),
        "is_exit": str(is_exit),
        "is_signal_flip": str(int(is_signal_flip)),
        "is_stop_loss": str(int(is_stop_loss)),
        # was_long: side held *before* this trade fires. The circuit's
        # signal-flip exit branches on it (HIGH #11 — short→long flips
        # were previously unprovable). Operator must declare honestly;
        # a wrong value fails the in-circuit threshold check.
        "was_long": str(int(was_long)),
        "expected_amount_out": str(expected_amount_out),
    }
    return WitnessRequest(
        strategy_class="momentum_v1",
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
    `amountIn` (the two MUST agree — `StrategyVault` enforces
    `publicInputs[PI_AMOUNT_IN] == swap.amountIn`).

    Two modes:

    * **Multi-decimal mode** (`asset_decimals` provided AND maps
      `intent.asset_in`): produces *raw* `tokenIn` units using the
      asset's actual decimals. Required when the universe has tokens
      with different decimals (Phase-6 multi-asset: mUSDC=18,
      mWBTC=8, mWETH=18, mSOL=9 on Kite testnet today; mUSDC=6 on
      mainnet). Without this, the swap router would receive an
      amount mismatched to `tokenIn`'s native decimals and the
      on-chain check would revert.

    * **Legacy mode** (`asset_decimals` is None / missing the asset):
      the Phase-1 USDC-only encoding — `amount_in` is USD * 10^18.
      Works only when the universe is uniformly 18-decimal AND the
      base asset is mUSDC-as-18-dec (Phase-1 demo). Kept for
      backward compatibility with the existing test corpus and any
      scenario harness that hasn't been migrated yet.

    The circuit doesn't interpret `amount_in` semantically beyond
    `amount_in <= max_position_size`. In multi-decimal mode that
    constraint becomes a loose upper bound (raw 8-dec WBTC amounts
    are tiny vs `max_position_size_usd * 10^18`); the tight USD
    cap is enforced off-chain by `StrategyAgent._size`.
    """
    asset_in = intent.asset_in
    dec = (asset_decimals or {}).get(asset_in)

    if intent.amount_in_usd is not None:
        if dec is not None:
            # USD-denominated leg in multi-decimal mode is always paired
            # with the stable as `asset_in` (LONG entry: USDC → asset).
            # Translate directly to the stable's raw decimals.
            return int(intent.amount_in_usd * 10**dec)
        return int(intent.amount_in_usd * 10**18)

    if intent.amount_in_asset is not None:
        if dec is not None:
            # Asset-denominated leg (EXIT: asset → USDC) carries the raw
            # asset quantity in human-readable units. Scale to raw.
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

    Mirrors `momentum_v1.circom` Constraints 2a/2b/2c:

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
        num = pow10_out * ONE_E18
        denom = pow10_in * last_price_e18
    else:
        num = pow10_out * last_price_e18
        denom = pow10_in * ONE_E18
    if denom == 0:
        raise ValueError("cross-decimal conversion denominator is zero")
    expected = (amount_in * num) // denom
    slip_term = expected * (10_000 - max_slippage_bps)
    min_amount_out = (slip_term + 9_999) // 10_000
    return expected, min_amount_out
