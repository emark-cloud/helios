"""`AllocatorOnChain.read_user_allocations` — rebuild a user's live
allocation set from on-chain `AllocatorVault.allocationOf`.

Paired with `read_user_meta_strategy`: the meta read restores *what the
user authorized*; this restores *where their capital actually is*, so a
post-restart dashboard shows real principal immediately instead of
zeros until the next cadence rebalance. These tests pin the
record→`AllocationState` decode (the empty-slot skip, the defunded
carry, the HWM-zero floor, the chain id) and the per-strategy
read-failure tolerance, with web3 faked so no RPC is dialled.
"""

from __future__ import annotations

import pytest
from helios_allocator.runtime.onchain import AllocatorOnChain

_USER = "0x" + "ab" * 20
_USER_VAULT = "0x" + "cd" * 20
_VAULT = "0x" + "22" * 20
_S1 = "0x" + "11" * 20
_S2 = "0x" + "33" * 20
_S3 = "0x" + "44" * 20


def _live_runner() -> AllocatorOnChain:
    r = AllocatorOnChain(
        rpc_url="http://stub:1",
        operator_pk="0x" + "11" * 32,
        allocator_vault_address=_VAULT,
        allocator_registry_address="0x" + "33" * 20,
        chain_id=2368,
        user_vault_address=_USER_VAULT,
    )
    # Decode-path only — don't dial RPC / parse the key.
    r._ensure_live = lambda: None  # type: ignore[method-assign]
    return r


class _Fn:
    def __init__(self, ret: object) -> None:
        self._ret = ret

    def call(self) -> object:
        if isinstance(self._ret, Exception):
            raise self._ret
        return self._ret


class _Functions:
    def __init__(self, table: dict[str, object]) -> None:
        self._table = table

    def allocationOf(self, _user: str, strategy: str) -> _Fn:
        return _Fn(self._table[strategy.lower()])


class _Contract:
    def __init__(self, table: dict[str, object]) -> None:
        self.functions = _Functions(table)


def _record(
    strategy: str,
    *,
    capital: int,
    hwm: int,
    defunded_at: int = 0,
    last_update: int = 123,
) -> tuple[object, ...]:
    # IAllocatorVault.AllocationRecord:
    # [0]=strategy [1]=capitalDeployed [2]=highWaterMark
    # [3]=defundedAt [4]=lastUpdate
    return (strategy, capital, hwm, defunded_at, last_update)


def test_returns_empty_in_stub_mode() -> None:
    stub = AllocatorOnChain(
        rpc_url="",
        operator_pk="",
        allocator_vault_address="",
        allocator_registry_address="",
        chain_id=2368,
    )
    assert stub.read_user_allocations(_USER, [_S1, _S2]) == []


@pytest.mark.asyncio
async def test_async_wrapper_empty_in_stub_mode() -> None:
    stub = AllocatorOnChain(
        rpc_url="",
        operator_pk="",
        allocator_vault_address="",
        allocator_registry_address="",
        chain_id=2368,
    )
    assert await stub.read_user_allocations_async(_USER, [_S1]) == []


def test_skips_empty_slots_and_keeps_funded() -> None:
    r = _live_runner()
    r._vault_contract = _Contract(  # type: ignore[assignment]
        {
            _S1.lower(): _record(_S1, capital=500 * 10**18, hwm=600 * 10**18),
            _S2.lower(): _record(_S2, capital=0, hwm=0),  # never allocated
            _S3.lower(): _record(_S3, capital=300 * 10**18, hwm=300 * 10**18),
        }
    )
    out = r.read_user_allocations(_USER, [_S1, _S2, _S3])
    by_id = {a.strategy_id: a for a in out}
    assert set(by_id) == {_S1, _S3}  # _S2 (empty slot) dropped
    assert by_id[_S1].capital_deployed_usd == 500 * 10**18
    assert by_id[_S1].high_water_mark_usd == 600 * 10**18
    assert by_id[_S1].nav_usd == 500 * 10**18  # seeded to principal
    assert by_id[_S1].chain_id == 2368  # this runner's chain
    assert by_id[_S1].declared_class == ""  # caller fills from directory
    assert by_id[_S1].defunded is False


def test_defunded_position_is_kept_and_flagged() -> None:
    r = _live_runner()
    r._vault_contract = _Contract(  # type: ignore[assignment]
        {_S1.lower(): _record(_S1, capital=0, hwm=400 * 10**18, defunded_at=1_777_000_000)}
    )
    out = r.read_user_allocations(_USER, [_S1])
    assert len(out) == 1
    assert out[0].defunded is True
    # capital==0 but defundedAt!=0 → still a real record, not a phantom row.
    assert out[0].strategy_id == _S1


def test_hwm_zero_falls_back_to_capital() -> None:
    r = _live_runner()
    r._vault_contract = _Contract(  # type: ignore[assignment]
        {_S1.lower(): _record(_S1, capital=250 * 10**18, hwm=0)}
    )
    out = r.read_user_allocations(_USER, [_S1])
    assert len(out) == 1
    # Matches how the loop seeds HWM at ALLOCATION_CREATED so drawdown
    # math stays consistent across a rehydrate.
    assert out[0].high_water_mark_usd == 250 * 10**18


def test_per_strategy_read_failure_is_swallowed() -> None:
    r = _live_runner()
    r._vault_contract = _Contract(  # type: ignore[assignment]
        {
            _S1.lower(): RuntimeError("rpc down on this address"),
            _S2.lower(): _record(_S2, capital=700 * 10**18, hwm=700 * 10**18),
        }
    )
    out = r.read_user_allocations(_USER, [_S1, _S2])
    # _S1 read raised → swallowed; _S2 still resolves.
    assert [a.strategy_id for a in out] == [_S2]
    assert out[0].capital_deployed_usd == 700 * 10**18


def test_all_empty_returns_empty_list() -> None:
    r = _live_runner()
    r._vault_contract = _Contract(  # type: ignore[assignment]
        {
            _S1.lower(): _record(_S1, capital=0, hwm=0),
            _S2.lower(): _record(_S2, capital=0, hwm=0),
        }
    )
    assert r.read_user_allocations(_USER, [_S1, _S2]) == []
