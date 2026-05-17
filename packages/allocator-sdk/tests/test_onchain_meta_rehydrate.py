"""`AllocatorOnChain.read_user_meta_strategy` — rebuild a user's
`MetaStrategy` from the on-chain `UserVault.metaStrategyOf` struct.

The chain is the source of truth: Sentinel's user store is in-process
and lost on restart, so the dashboard rehydrates from this read. These
tests pin the struct→SDK decode (units, slug mapping, the zero-struct
"never onboarded" sentinel) and the stub-mode boundary, with web3 faked
so no RPC is dialled.
"""

from __future__ import annotations

import pytest
from helios_allocator.runtime.onchain import AllocatorOnChain
from helios_contracts_abi.class_ids import MEAN_REVERSION_V1, MOMENTUM_V1

_USDC = "0x" + "11" * 20
_USER = "0x" + "ab" * 20
_USER_VAULT = "0x" + "cd" * 20


def _live_runner() -> AllocatorOnChain:
    r = AllocatorOnChain(
        rpc_url="http://stub:1",
        operator_pk="0x" + "11" * 32,
        allocator_vault_address="0x" + "22" * 20,
        allocator_registry_address="0x" + "33" * 20,
        chain_id=2368,
        user_vault_address=_USER_VAULT,
    )
    # Don't dial / parse the key — we only exercise the decode path.
    r._ensure_live = lambda: None  # type: ignore[method-assign]
    return r


class _Fn:
    def __init__(self, ret: object) -> None:
        self._ret = ret

    def call(self) -> object:
        return self._ret


class _Functions:
    def __init__(self, ret: object) -> None:
        self._ret = ret

    def metaStrategyOf(self, _addr: str) -> _Fn:
        return _Fn(self._ret)


class _Contract:
    def __init__(self, ret: object) -> None:
        self.functions = _Functions(ret)


class _Eth:
    def __init__(self, ret: object) -> None:
        self._ret = ret

    def contract(self, *, address: str, abi: object) -> _Contract:
        return _Contract(self._ret)


class _W3:
    def __init__(self, ret: object) -> None:
        self.eth = _Eth(ret)


def _struct(
    *,
    classes: list[bytes],
    max_capital: int,
    valid_until: int = 9_999_999_999,
) -> tuple[object, ...]:
    return (
        b"\x00" * 32,  # metaStrategyHash
        classes,  # allowedStrategyClasses
        [_USDC],  # allowedAssets (placeholder on-chain; decode drops it)
        [2368],  # allowedChains
        max_capital,  # maxCapital (usd * 1e18)
        3_500,  # maxPerStrategyBps
        5,  # maxStrategiesCount
        1_500,  # drawdownThresholdBps
        500,  # maxFeeRateBps
        1_800,  # rebalanceCadenceSec
        valid_until,  # validUntil
        3,  # defundTwapBars
        50,  # defundBondBps
        25,  # defundConfirmBlocks
    )


def test_returns_none_in_stub_mode() -> None:
    stub = AllocatorOnChain(
        rpc_url="",
        operator_pk="",
        allocator_vault_address="",
        allocator_registry_address="",
        chain_id=2368,
    )
    assert stub.read_user_meta_strategy(_USER) is None


@pytest.mark.asyncio
async def test_async_wrapper_none_in_stub_mode() -> None:
    stub = AllocatorOnChain(
        rpc_url="",
        operator_pk="",
        allocator_vault_address="",
        allocator_registry_address="",
        chain_id=2368,
    )
    assert await stub.read_user_meta_strategy_async(_USER) is None


def test_zero_struct_is_treated_as_no_meta() -> None:
    r = _live_runner()
    r._w3 = _W3(_struct(classes=[], max_capital=0, valid_until=0))  # type: ignore[assignment]
    assert r.read_user_meta_strategy(_USER) is None


def test_decodes_onchain_struct_to_sdk_meta() -> None:
    r = _live_runner()
    r._w3 = _W3(  # type: ignore[assignment]
        _struct(classes=[MOMENTUM_V1, MEAN_REVERSION_V1], max_capital=2_000 * 10**18)
    )
    meta = r.read_user_meta_strategy(_USER)
    assert meta is not None
    # bytes32 class ids → human slugs the allocator's class_fit expects.
    assert list(meta.allowed_strategy_classes) == ["momentum_v1", "mean_reversion_v1"]
    # maxCapital (wei) → human USD (the unit the store + loop expect).
    assert meta.max_capital_usd == 2_000
    assert list(meta.allowed_chains) == [2368]
    # allowed_assets is unused by the allocator + unrecoverable on-chain.
    assert list(meta.allowed_assets) == []
    assert meta.max_per_strategy_bps == 3_500
    assert meta.max_strategies_count == 5
    assert meta.drawdown_threshold_bps == 1_500
    assert meta.max_fee_rate_bps == 500
    assert meta.rebalance_cadence_sec == 1_800
    assert meta.valid_until == 9_999_999_999
    assert meta.user_address.lower() == _USER.lower()


def test_unknown_class_id_falls_back_to_hex() -> None:
    r = _live_runner()
    unknown = b"\xde" * 32
    r._w3 = _W3(_struct(classes=[unknown], max_capital=10**18))  # type: ignore[assignment]
    meta = r.read_user_meta_strategy(_USER)
    assert meta is not None
    assert list(meta.allowed_strategy_classes) == ["0x" + "de" * 32]


def test_read_failure_returns_none() -> None:
    r = _live_runner()

    class _Boom:
        @property
        def eth(self) -> object:
            raise RuntimeError("rpc down")

    r._w3 = _Boom()  # type: ignore[assignment]
    assert r.read_user_meta_strategy(_USER) is None
