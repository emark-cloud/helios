"""OnChainRunner unit tests.

Two layers:

1. **Dry-run** — when no allocator vault address is set, calls accumulate
   in `pending` instead of submitting. Already covered indirectly by
   `test_loop.py`; restated here as a focused contract.
2. **Live calldata encoding** — exercises `_build_function` against the
   ABI without an actual RPC. Catches encoder regressions (wrong
   function selector, wrong arg order) without needing anvil.

Live tx submission itself is exercised end-to-end by
`scripts/e2e-scenario.sh` against the docker-compose anvil-kite. We
don't add a separate per-test RPC harness — that would duplicate the
e2e infrastructure for marginal extra confidence.
"""

from __future__ import annotations

import pytest
from sentinel.onchain import OnChainCall, OnChainRunner

_ZERO_ADDR = "0x" + "00" * 20
_USER = "0x" + "11" * 20
_STRAT = "0x" + "22" * 20
_VAULT = "0x" + "33" * 20
_REGISTRY = "0x" + "44" * 20
_OPERATOR_PK = "0x" + "ab" * 32  # any valid 32-byte key


def _dry_runner() -> OnChainRunner:
    return OnChainRunner(
        rpc_url="",
        operator_pk="",
        allocator_vault_address="",
        allocator_registry_address="",
        chain_id=2368,
    )


def _live_runner() -> OnChainRunner:
    # `rpc_url` is a real-looking string but the runner only opens a
    # connection on first submit — calldata encoding goes through the
    # contract object's ABI, not RPC. _ensure_live() is called eagerly
    # on first encode attempt; it will succeed because Web3 doesn't
    # ping the endpoint at construction time.
    return OnChainRunner(
        rpc_url="http://127.0.0.1:1",  # never dialled in this test
        operator_pk=_OPERATOR_PK,
        allocator_vault_address=_VAULT,
        allocator_registry_address=_REGISTRY,
        chain_id=2368,
    )


# ── Dry-run ───────────────────────────────────────────────────


def test_dry_run_records_calls_without_submitting() -> None:
    r = _dry_runner()
    assert r.live is False

    r.allocate(_USER, _STRAT, 1_000)
    r.defund(_USER, _STRAT, "DRAWDOWN_BREACH")
    r.settle_fee(_USER, _STRAT)
    r.rebalance(_USER, [_STRAT, _ZERO_ADDR], [6_000, 4_000])

    methods = [c.method for c in r.pending]
    assert methods == [
        "allocateToStrategy",
        "defundStrategy",
        "settleStrategyFee",
        "rebalance",
    ]
    # Dry-run never sets tx_hash / submitted.
    assert all(c.tx_hash == "" and not c.submitted for c in r.pending)


# ── Live calldata encoding ────────────────────────────────────


def test_build_function_allocate_encodes_to_correct_selector() -> None:
    r = _live_runner()
    r._ensure_live()
    call = OnChainCall(method="allocateToStrategy", user=_USER, strategy=_STRAT, amount=1_000)
    fn = r._build_function(call)
    # web3 builds the call object lazily; trigger encoding via _encode_transaction_data.
    data = fn._encode_transaction_data()
    # keccak256("allocateToStrategy(address,address,uint256)")[:4]
    assert data.startswith("0xe5130322")


def test_build_function_defund_encodes_string_reason() -> None:
    r = _live_runner()
    r._ensure_live()
    call = OnChainCall(
        method="defundStrategy", user=_USER, strategy=_STRAT, reason="DRAWDOWN_BREACH"
    )
    fn = r._build_function(call)
    data = fn._encode_transaction_data()
    # keccak256("defundStrategy(address,address,string)")[:4]
    assert data.startswith("0xf1b1c6c8")


def test_build_function_rebalance_encodes_arrays() -> None:
    r = _live_runner()
    r._ensure_live()
    call = OnChainCall(
        method="rebalance",
        user=_USER,
        strategy=None,
        strategies=(_STRAT, _ZERO_ADDR),
        weights_bps=(6_000, 4_000),
    )
    fn = r._build_function(call)
    data = fn._encode_transaction_data()
    # keccak256("rebalance(address,address[],uint256[])")[:4]
    assert data.startswith("0xe6d508ea")


def test_build_function_unknown_method_raises() -> None:
    r = _live_runner()
    r._ensure_live()

    with pytest.raises(ValueError, match="unknown onchain method"):
        r._build_function(OnChainCall(method="bogus", user=_USER, strategy=_STRAT))
