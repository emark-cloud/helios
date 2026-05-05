"""Dry-run mode tests for `AllocatorOnChain`.

Live-mode submission (web3 + signed tx + receipt wait) is exercised by
the Sentinel integration tests against an anvil instance — those run in
`services/sentinel/tests/test_onchain.py` and equivalent. Here we only
need to confirm the dry-run boundary: methods record planned calls,
return them, and don't try to talk to web3.
"""

from __future__ import annotations

import pytest
from helios_allocator.runtime.onchain import AllocatorOnChain, OnChainCall


@pytest.fixture
def stub_runner() -> AllocatorOnChain:
    return AllocatorOnChain(
        rpc_url="",
        operator_pk="",
        allocator_vault_address="",
        allocator_registry_address="",
        chain_id=2368,
    )


def test_dry_run_mode_inactive_with_empty_config(stub_runner: AllocatorOnChain) -> None:
    assert stub_runner.live is False


def test_allocate_records_call(stub_runner: AllocatorOnChain) -> None:
    call = stub_runner.allocate("0xuser", "0xstrategy", 5_000)
    assert isinstance(call, OnChainCall)
    assert call.method == "allocateToStrategy"
    assert call.amount == 5_000
    assert stub_runner.pending == [call]


def test_defund_records_call(stub_runner: AllocatorOnChain) -> None:
    call = stub_runner.defund("0xuser", "0xstrategy", "DRAWDOWN_BREACH")
    assert call.method == "defundStrategy"
    assert call.reason == "DRAWDOWN_BREACH"
    assert stub_runner.pending[-1] is call


def test_rebalance_records_weights(stub_runner: AllocatorOnChain) -> None:
    call = stub_runner.rebalance("0xuser", ["0xa", "0xb"], [6_000, 4_000])
    assert call.method == "rebalance"
    assert call.strategies == ("0xa", "0xb")
    assert call.weights_bps == (6_000, 4_000)


def test_settle_fee_records_call(stub_runner: AllocatorOnChain) -> None:
    call = stub_runner.settle_fee("0xuser", "0xstrategy")
    assert call.method == "settleStrategyFee"


@pytest.mark.asyncio
async def test_async_wrappers_run_off_thread(stub_runner: AllocatorOnChain) -> None:
    call = await stub_runner.allocate_async("0xuser", "0xstrategy", 1)
    assert call.method == "allocateToStrategy"
    call = await stub_runner.defund_async("0xuser", "0xstrategy", "RANK_DROP")
    assert call.method == "defundStrategy"
    call = await stub_runner.rebalance_async("0xuser", ["0xa"], [10_000])
    assert call.method == "rebalance"
    call = await stub_runner.settle_fee_async("0xuser", "0xstrategy")
    assert call.method == "settleStrategyFee"


@pytest.mark.asyncio
async def test_read_allocation_returns_none_when_not_live(
    stub_runner: AllocatorOnChain,
) -> None:
    assert await stub_runner.read_allocation("0xuser", "0xstrategy") is None


def test_register_allocator_dry_run(stub_runner: AllocatorOnChain) -> None:
    """Register is a no-op in dry-run; returns the configured vault."""
    out = stub_runner.register_allocator(
        name="MyAllocator",
        ranking_function_hash=b"\x00" * 32,
        supported_classes=[b"\x00" * 32],
        fee_rate_bps=500,
        stake_amount=10_000,
    )
    assert out == ""  # vault address is empty in stub mode
