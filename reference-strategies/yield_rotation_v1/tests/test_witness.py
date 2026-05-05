"""Witness-builder invariants for `yield_rotation_v1`.

Asserts the witness shape matches `gen-fixture-yr.js` (12 PIs + private
witness) and that vector parity holds for the canonical fixture inputs.
"""

from __future__ import annotations

import pytest
from yield_rotation_v1.types import RotationIntent, YieldTick
from yield_rotation_v1.witness import (
    ALLOW_TREE_DEPTH,
    YIELD_TREE_DEPTH,
    build_yield_rotation_witness,
    reconstruct_allowlist_root,
    reconstruct_yield_root,
)

# Canonical fixture (matches gen-fixture-yr.js).
FIXTURE_SNAPSHOTS = [
    YieldTick(market_id=1, apy_bps_e6=420 * 1_000_000, timestamp_ms=1),
    YieldTick(market_id=2, apy_bps_e6=550 * 1_000_000, timestamp_ms=1),
    YieldTick(market_id=3, apy_bps_e6=380 * 1_000_000, timestamp_ms=1),
    YieldTick(market_id=4, apy_bps_e6=500 * 1_000_000, timestamp_ms=1),
]
FIXTURE_ALLOWLIST = [1, 2, 3, 4]
FIXTURE_INTENT = RotationIntent(
    m_from=1,
    m_to=2,
    amount_in_usd=1.0,  # → 1e18 amount_rotating
    apy_from_bps=420,
    apy_to_bps=550,
)
FIXTURE_DECLARED_CLASS = 0x9ABC
FIXTURE_STRATEGY_VAULT = "0xc0ffee0c0ffee0c0ffee0c0ffee0c0ffee0c0ffee"
FIXTURE_ALLOCATOR = "0xa11ca7"
FIXTURE_NONCE = 7
FIXTURE_BLOCK_END = 200
FIXTURE_BLOCK_START = 150
FIXTURE_THRESHOLD = 80
FIXTURE_BRIDGING = 30

# Computed by `circuits/scripts/gen-fixture-yr.js` against the 13-PI
# circuit (followup #5 — block_window_start added). Re-run the
# generator script to refresh after any PI / params_hash change.
EXPECTED_TRADE_HASH = 3723609009985288208521441901558949253503109140460325761007469747154611652486
EXPECTED_YIELD_ROOT = 19617008100108992903905573385623852931387633461552456891295159462318722212376


def _build_fixture_witness():
    return build_yield_rotation_witness(
        intent=FIXTURE_INTENT,
        yield_snapshots=FIXTURE_SNAPSHOTS,
        allowlisted_markets=FIXTURE_ALLOWLIST,
        declared_class_field=FIXTURE_DECLARED_CLASS,
        strategy_vault=FIXTURE_STRATEGY_VAULT,
        allocator_address=FIXTURE_ALLOCATOR,
        nonce=FIXTURE_NONCE,
        block_window_end=FIXTURE_BLOCK_END,
        block_window_start=FIXTURE_BLOCK_START,
        signal_threshold_bps=FIXTURE_THRESHOLD,
        bridging_cost_bps=FIXTURE_BRIDGING,
    )


def test_witness_strategy_class_is_yield_rotation_v1() -> None:
    req = _build_fixture_witness()
    assert req.strategy_class == "yield_rotation_v1"


def test_witness_trade_hash_matches_js_fixture() -> None:
    req = _build_fixture_witness()
    assert req.trade_hash == EXPECTED_TRADE_HASH
    assert int(req.inputs["trade_hash"]) == EXPECTED_TRADE_HASH


def test_witness_yield_root_matches_js_fixture() -> None:
    req = _build_fixture_witness()
    assert req.yield_root == EXPECTED_YIELD_ROOT
    assert int(req.inputs["yield_oracle_root"]) == EXPECTED_YIELD_ROOT


def test_witness_input_keys_complete() -> None:
    req = _build_fixture_witness()
    expected_keys = {
        # 13 public
        "trade_hash",
        "declared_class",
        "strategy_vault",
        "params_hash",
        "markets_allowlist_root",
        "m_from",
        "m_to",
        "amount_rotating",
        "yield_oracle_root",
        "allocator_address",
        "nonce",
        "block_window_end",
        "block_window_start",
        # private
        "apy_from",
        "apy_to",
        "signal_threshold",
        "bridging_cost",
        "yield_path_indices_from",
        "yield_siblings_from",
        "yield_path_indices_to",
        "yield_siblings_to",
        "allow_path_indices_from",
        "allow_siblings_from",
        "allow_path_indices_to",
        "allow_siblings_to",
    }
    assert set(req.inputs.keys()) == expected_keys


def test_witness_inclusion_proof_lengths_match_depths() -> None:
    req = _build_fixture_witness()
    assert len(req.inputs["yield_path_indices_from"]) == YIELD_TREE_DEPTH
    assert len(req.inputs["yield_siblings_from"]) == YIELD_TREE_DEPTH
    assert len(req.inputs["yield_path_indices_to"]) == YIELD_TREE_DEPTH
    assert len(req.inputs["yield_siblings_to"]) == YIELD_TREE_DEPTH
    assert len(req.inputs["allow_path_indices_from"]) == ALLOW_TREE_DEPTH
    assert len(req.inputs["allow_siblings_from"]) == ALLOW_TREE_DEPTH


def test_witness_amount_is_e18() -> None:
    req = _build_fixture_witness()
    assert int(req.inputs["amount_rotating"]) == 10**18


def test_witness_rejects_below_threshold_differential() -> None:
    intent = RotationIntent(m_from=1, m_to=2, amount_in_usd=1.0, apy_from_bps=420, apy_to_bps=525)
    with pytest.raises(ValueError, match="below threshold"):
        build_yield_rotation_witness(
            intent=intent,
            yield_snapshots=[
                YieldTick(market_id=1, apy_bps_e6=420 * 1_000_000, timestamp_ms=1),
                YieldTick(market_id=2, apy_bps_e6=525 * 1_000_000, timestamp_ms=1),
            ],
            allowlisted_markets=[1, 2],
            declared_class_field=1,
            strategy_vault="0x" + "0" * 40,
            allocator_address="0x" + "0" * 40,
            nonce=1,
            block_window_end=100,
            block_window_start=50,
            signal_threshold_bps=80,
            bridging_cost_bps=30,
        )


def test_witness_rejects_non_allowlisted_market() -> None:
    intent = RotationIntent(m_from=1, m_to=99, amount_in_usd=1.0, apy_from_bps=420, apy_to_bps=550)
    with pytest.raises(ValueError, match="allowlist"):
        build_yield_rotation_witness(
            intent=intent,
            yield_snapshots=FIXTURE_SNAPSHOTS,
            allowlisted_markets=FIXTURE_ALLOWLIST,
            declared_class_field=1,
            strategy_vault="0x" + "0" * 40,
            allocator_address="0x" + "0" * 40,
            nonce=1,
            block_window_end=100,
            block_window_start=50,
            signal_threshold_bps=80,
            bridging_cost_bps=30,
        )


def test_witness_rejects_missing_snapshot() -> None:
    intent = RotationIntent(m_from=1, m_to=2, amount_in_usd=1.0, apy_from_bps=420, apy_to_bps=550)
    # Snapshot for m_to=2 is missing.
    with pytest.raises(ValueError, match="yield snapshot missing"):
        build_yield_rotation_witness(
            intent=intent,
            yield_snapshots=[
                YieldTick(market_id=1, apy_bps_e6=420 * 1_000_000, timestamp_ms=1),
                YieldTick(market_id=3, apy_bps_e6=550 * 1_000_000, timestamp_ms=1),
            ],
            allowlisted_markets=[1, 2, 3],
            declared_class_field=1,
            strategy_vault="0x" + "0" * 40,
            allocator_address="0x" + "0" * 40,
            nonce=1,
            block_window_end=100,
            block_window_start=50,
            signal_threshold_bps=80,
            bridging_cost_bps=30,
        )


def test_reconstruct_helpers_produce_matching_roots() -> None:
    yield_root = reconstruct_yield_root(FIXTURE_SNAPSHOTS)
    allow_root = reconstruct_allowlist_root(FIXTURE_ALLOWLIST)
    assert yield_root == EXPECTED_YIELD_ROOT
    # allowlist root not directly fixture-pinned; just ensure determinism
    assert allow_root == reconstruct_allowlist_root(FIXTURE_ALLOWLIST)
