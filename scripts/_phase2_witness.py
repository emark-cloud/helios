"""Phase-2 e2e witness shims — thin adapters over the SDK builders.

Priority-3 follow-up #12: previously this module re-implemented the
witness logic from scratch because the SDK builders were broken. They
were fixed in WS6 PR2 (real Poseidon completions, full
strategy_vault/params_hash PIs). The e2e now exercises those SDK
builders directly so any regression in the public surface — momentum,
mean-reversion, yield-rotation — is caught by the integration scenario
rather than slipping past unit tests.

Each shim adapts the e2e's flat keyword API to the SDK builder's
intent-shaped API, then re-exposes the result as the dataclass the e2e
already consumes (so the call sites in `e2e_scenario_phase2.py` don't
move).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from helios.types import Direction, TradeIntent
from helios_contracts_abi.class_ids import class_id_as_field
from mean_reversion_v1.witness import (
    UNIVERSE_SIZE as MR_UNIVERSE_SIZE,
)
from mean_reversion_v1.witness import (
    build_mean_reversion_witness as _sdk_build_mr,
)
from momentum_v1.witness import (
    UNIVERSE_SIZE as MOM_UNIVERSE_SIZE,
)
from momentum_v1.witness import (
    build_momentum_witness as _sdk_build_momentum,
)
from yield_rotation_v1.types import RotationIntent, YieldTick
from yield_rotation_v1.witness import (
    build_yield_rotation_witness as _sdk_build_yr,
)

PRICE_OBSERVATIONS = 16

# Synthetic asset universe used by the e2e — the SDK requires 8
# entries, but the e2e only exercises a single asset pair (idx 0). We
# seed both `asset_in` and `asset_out` to "ASSET0" so the witness
# carries (asset_in_idx, asset_out_idx) = (0, 0), matching the
# pre-shim behaviour of `_phase2_witness`.
_E2E_ASSET = "ASSET0"
_E2E_UNIVERSE: list[str] = [f"ASSET{i}" for i in range(MOM_UNIVERSE_SIZE)]
assert MOM_UNIVERSE_SIZE == MR_UNIVERSE_SIZE, "momentum and MR universe sizes must agree"
_E2E_ASSET_IDX: dict[str, int] = {a: i for i, a in enumerate(_E2E_UNIVERSE)}


# ── momentum_v1 ───────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class MomentumWitness:
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
    amount_in: int = 1 * 10**18,
) -> MomentumWitness:
    """Adapter: e2e flat kwargs → SDK builder. Direction is fixed to
    LONG since the e2e only drives long-entry trades; the SDK's
    `_resolve_amount_in_e18` honours the provided `amount_in_usd`."""
    if len(price_observations_e18) != PRICE_OBSERVATIONS:
        raise ValueError(f"price_observations_e18 must be exactly {PRICE_OBSERVATIONS} bars")
    if amount_in > max_position_size:
        raise ValueError("amount_in > max_position_size violates circuit constraint 1")

    intent = TradeIntent(
        asset_in=_E2E_ASSET,
        asset_out=_E2E_ASSET,
        direction=Direction.LONG,
        amount_in_usd=amount_in / 10**18,
        max_slippage_bps=max_slippage_bps,
    )
    req = _sdk_build_momentum(
        intent=intent,
        asset_to_universe_idx=_E2E_ASSET_IDX,
        asset_universe_addresses=_E2E_UNIVERSE,
        price_observations_e18=price_observations_e18,
        declared_class_field=class_id_as_field("momentum_v1"),
        strategy_vault_address=strategy_vault,
        allocator_address=allocator_vault,
        nonce=nonce,
        block_window_start=block_window_start,
        block_window_end=block_window_end,
        max_position_size_e18=max_position_size,
        max_slippage_bps=max_slippage_bps,
        signal_threshold_bps=signal_threshold_bps,
        stop_loss_price_e18=stop_loss_price,
        is_signal_flip=False,
        is_stop_loss=False,
    )
    return MomentumWitness(
        inputs=req.inputs,
        params_hash=req.params_hash,
        oracle_root=req.oracle_root,
    )


# ── mean_reversion_v1 ─────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class MeanReversionWitness:
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
    amount_in: int = 1 * 10**18,
) -> MeanReversionWitness:
    """Adapter: e2e flat kwargs → SDK builder. Defaults track
    `gen-fixture-mr.js` (15 bars at one price, last bar deep dip);
    long-entry semantics."""
    if len(price_observations) != PRICE_OBSERVATIONS:
        raise ValueError(f"price_observations must be exactly {PRICE_OBSERVATIONS} bars")
    if amount_in > max_position_size:
        raise ValueError("amount_in > max_position_size violates circuit constraint 1")
    sum_total = sum(price_observations)
    if 16 * price_observations[15] >= sum_total:
        raise ValueError(
            "long entry requires price_last below the 16-bar mean "
            "(sum_total > 16 * price_observations[15])"
        )

    intent = TradeIntent(
        asset_in=_E2E_ASSET,
        asset_out=_E2E_ASSET,
        direction=Direction.LONG,
        amount_in_usd=amount_in / 10**18,
        max_slippage_bps=max_slippage_bps,
    )
    req = _sdk_build_mr(
        intent=intent,
        asset_to_universe_idx=_E2E_ASSET_IDX,
        asset_universe_addresses=_E2E_UNIVERSE,
        price_observations_e18=price_observations,
        declared_class_field=class_id_as_field("mean_reversion_v1"),
        strategy_vault_address=strategy_vault,
        allocator_address=allocator_vault,
        nonce=nonce,
        block_window_start=block_window_start,
        block_window_end=block_window_end,
        max_position_size_e18=max_position_size,
        max_slippage_bps=max_slippage_bps,
        n_sigma_x100=n_sigma_x100,
        stop_loss_price_e18=stop_loss_price,
        is_signal_flip=False,
        is_stop_loss=False,
    )
    return MeanReversionWitness(
        inputs=req.inputs,
        params_hash=req.params_hash,
        oracle_root=req.oracle_root,
    )


# ── yield_rotation_v1 ─────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class YieldRotationWitness:
    inputs: dict[str, Any]
    yield_oracle_root: int
    markets_allowlist_root: int
    params_hash: bytes


# Canonical 4-market test cosmos. Mirrors `gen-fixture-yr.js` so the
# witness shape is identical to the verifier-only fixture, but
# parameterized per-call for allocator + nonce.
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
    """Adapter: e2e flat kwargs → SDK builder. Defaults mirror
    `gen-fixture-yr.js`: AAVE_USDC (420 bps) → COMPOUND_USDC (550 bps),
    threshold 80, bridging 30 ⇒ differential 130 ≥ 110 (Constraint 6)."""
    if from_market not in _MARKETS or to_market not in _MARKETS:
        raise ValueError(f"unknown market in {(from_market, to_market)!r}")
    if from_market == to_market:
        raise ValueError("from_market == to_market violates Constraint 5")

    snapshots = [
        YieldTick(market_id=_MARKETS[m], apy_bps_e6=_APY_BPS[m] * 1_000_000, timestamp_ms=1)
        for m in _MARKET_ORDER
    ]
    allowlist = [_MARKETS[m] for m in _MARKET_ORDER]
    intent = RotationIntent(
        m_from=_MARKETS[from_market],
        m_to=_MARKETS[to_market],
        amount_in_usd=amount_rotating / 10**18,
        apy_from_bps=_APY_BPS[from_market],
        apy_to_bps=_APY_BPS[to_market],
    )
    req = _sdk_build_yr(
        intent=intent,
        yield_snapshots=snapshots,
        allowlisted_markets=allowlist,
        declared_class_field=class_id_as_field("yield_rotation_v1"),
        strategy_vault=strategy_vault,
        allocator_address=allocator_vault,
        nonce=nonce,
        block_window_end=block_window_end,
        block_window_start=block_window_start,
        signal_threshold_bps=signal_threshold_bps,
        bridging_cost_bps=bridging_cost_bps,
    )
    params_hash_int = int(req.inputs["params_hash"])
    return YieldRotationWitness(
        inputs=req.inputs,
        yield_oracle_root=req.yield_root,
        markets_allowlist_root=req.allowlist_root,
        params_hash=params_hash_int.to_bytes(32, "big"),
    )


__all__ = [
    "PRICE_OBSERVATIONS",
    "MeanReversionWitness",
    "MomentumWitness",
    "YieldRotationWitness",
    "build_mean_reversion_witness",
    "build_momentum_witness",
    "build_yield_rotation_witness",
]
