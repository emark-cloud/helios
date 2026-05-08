"""WS4 — Aave V3 Pool calldata shape.

`supply(asset, amount, onBehalfOf, referralCode)` and
`withdraw(asset, amount, to)` are the only two write entry points
yield_rotation_v1 ever calls on the Pool. Pin the selectors and
the 4 / 3-word ABI layout against an independent decoder.
"""

from __future__ import annotations

import pytest
from eth_abi.abi import decode as abi_decode
from eth_utils.crypto import keccak
from yield_rotation_v1.aave_v3 import (
    RAY,
    build_aave_supply_calldata,
    build_aave_withdraw_calldata,
    build_current_liquidity_rate_calldata,
    ray_to_apy_bps,
)
from yield_rotation_v1.executor import TradeExecutor

_USDC = "0x036cbd53842c5426634e7929541ec2318f3dcf7e"
_USDT = "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9"
_VAULT = "0x000000000000000000000000000000000000beef"


def test_supply_selector_matches_canonical() -> None:
    expected = keccak(b"supply(address,uint256,address,uint16)")[:4]
    data = build_aave_supply_calldata(asset=_USDC, amount=1_000_000, on_behalf_of=_VAULT)
    assert data[:4] == expected


def test_withdraw_selector_matches_canonical() -> None:
    expected = keccak(b"withdraw(address,uint256,address)")[:4]
    data = build_aave_withdraw_calldata(asset=_USDC, amount=1_000_000, to=_VAULT)
    assert data[:4] == expected


def test_supply_payload_decodes_round_trip() -> None:
    data = build_aave_supply_calldata(
        asset=_USDC,
        amount=10_000_000,
        on_behalf_of=_VAULT,
        referral_code=42,
    )
    decoded = abi_decode(["address", "uint256", "address", "uint16"], data[4:])
    assert decoded[0].lower() == _USDC.lower()
    assert decoded[1] == 10_000_000
    assert decoded[2].lower() == _VAULT.lower()
    assert decoded[3] == 42


def test_withdraw_payload_decodes_round_trip_max_uint() -> None:
    full_exit = 2**256 - 1
    data = build_aave_withdraw_calldata(asset=_USDT, amount=full_exit, to=_VAULT)
    decoded = abi_decode(["address", "uint256", "address"], data[4:])
    assert decoded[0].lower() == _USDT.lower()
    assert decoded[1] == full_exit
    assert decoded[2].lower() == _VAULT.lower()


def test_current_liquidity_rate_calldata_shape() -> None:
    data = build_current_liquidity_rate_calldata(asset=_USDC)
    expected = keccak(b"currentLiquidityRate(address)")[:4]
    assert data[:4] == expected
    decoded = abi_decode(["address"], data[4:])
    assert decoded[0].lower() == _USDC.lower()


def test_ray_to_apy_bps() -> None:
    # 5% APY in ray = 0.05 * 1e27.
    rate = (RAY * 5) // 100
    assert ray_to_apy_bps(rate) == 500


def test_supply_rejects_symbolic_asset() -> None:
    with pytest.raises(ValueError, match="0x-prefixed address"):
        build_aave_supply_calldata(asset="USDC", amount=1, on_behalf_of=_VAULT)


def test_supply_rejects_negative_amount() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        build_aave_supply_calldata(asset=_USDC, amount=-1, on_behalf_of=_VAULT)


def test_executor_aave_rotation_packs_two_calls() -> None:
    executor = TradeExecutor(
        rpc_url="",
        operator_pk="",
        strategy_vault_address="",
        chain_id=421_614,
        lending_pool_address="0xBfC91D59fdAA134A4ED45f7B584cAf96D7792Eff",
        venue_kind="aave_v3",
    )
    calls = executor.build_aave_rotation_calls(
        from_asset=_USDC,
        to_asset=_USDT,
        amount=1_000_000,
        on_behalf_of=_VAULT,
    )
    assert len(calls) == 2
    assert calls[0].target.lower() == "0xbfc91d59fdaa134a4ed45f7b584caf96d7792eff"
    assert calls[1].target.lower() == "0xbfc91d59fdaa134a4ed45f7b584caf96d7792eff"
    # First call is withdraw of from_asset, second is supply of to_asset.
    withdraw_selector = keccak(b"withdraw(address,uint256,address)")[:4]
    supply_selector = keccak(b"supply(address,uint256,address,uint16)")[:4]
    assert calls[0].data[:4] == withdraw_selector
    assert calls[1].data[:4] == supply_selector
    # Decoded asset on each call matches its leg.
    decoded_w = abi_decode(["address", "uint256", "address"], calls[0].data[4:])
    decoded_s = abi_decode(["address", "uint256", "address", "uint16"], calls[1].data[4:])
    assert decoded_w[0].lower() == _USDC.lower()
    assert decoded_s[0].lower() == _USDT.lower()


def test_executor_aave_rotation_no_op_when_pool_unset() -> None:
    executor = TradeExecutor(
        rpc_url="",
        operator_pk="",
        strategy_vault_address="",
        chain_id=2368,
    )
    calls = executor.build_aave_rotation_calls(
        from_asset=_USDC,
        to_asset=_USDT,
        amount=1_000_000,
        on_behalf_of=_VAULT,
    )
    assert calls == []


def test_executor_passive_venue_rejects_aave_packer() -> None:
    executor = TradeExecutor(
        rpc_url="",
        operator_pk="",
        strategy_vault_address="",
        chain_id=2368,
        lending_pool_address="0xBfC91D59fdAA134A4ED45f7B584cAf96D7792Eff",
        venue_kind="passive",
    )
    with pytest.raises(RuntimeError, match="venue_kind=aave_v3"):
        executor.build_aave_rotation_calls(
            from_asset=_USDC,
            to_asset=_USDT,
            amount=1,
            on_behalf_of=_VAULT,
        )
