"""WS4 — Uniswap V3 SwapRouter02 calldata shape.

Pins the 4-byte selector + 8 × 32-byte word layout for
`exactInputSingle` so a future refactor can't silently drift the
ABI. Independent decoder uses `eth_abi` against the canonical V3
tuple — if Uniswap ever ships a v4 router with a different layout,
this test fails loudly rather than miscoding a real trade.
"""

from __future__ import annotations

from eth_abi.abi import decode as abi_decode
from eth_utils.crypto import keccak
from momentum_v1.executor import TradeExecutor

_RECIPIENT = "0x000000000000000000000000000000000000beef"
_TOKEN_IN = "0x4200000000000000000000000000000000000006"  # WETH on Base Sepolia
_TOKEN_OUT = "0x036cbd53842c5426634e7929541ec2318f3dcf7e"  # USDC on Base Sepolia


def _executor_v3() -> TradeExecutor:
    # Live mode disabled: empty rpc/operator/vault keeps the executor
    # in dry-run, but the calldata builder doesn't depend on those.
    return TradeExecutor(
        rpc_url="",
        operator_pk="",
        strategy_vault_address="",
        mock_router_address="0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4",
        chain_id=84_532,
        venue_kind="uniswap_v3",
        pool_fee_bps=500,
    )


def test_uniswap_v3_selector_matches_canonical() -> None:
    expected = keccak(
        b"exactInputSingle((address,address,uint24,address,uint256,uint256,uint256,uint160))"
    )[:4]
    data = _executor_v3().build_uniswap_v3_calldata(
        token_in=_TOKEN_IN,
        token_out=_TOKEN_OUT,
        recipient=_RECIPIENT,
        amount_in=10_000_000,
        amount_out_minimum=9_900_000,
        deadline_unix=1_777_500_000,
    )
    assert data[:4] == expected


def test_uniswap_v3_payload_decodes_round_trip() -> None:
    data = _executor_v3().build_uniswap_v3_calldata(
        token_in=_TOKEN_IN,
        token_out=_TOKEN_OUT,
        recipient=_RECIPIENT,
        amount_in=10_000_000,
        amount_out_minimum=9_900_000,
        deadline_unix=1_777_500_000,
        fee=3000,
    )
    # Strip selector and decode the 8-field tuple.
    decoded = abi_decode(
        [
            "(address,address,uint24,address,uint256,uint256,uint256,uint160)",
        ],
        data[4:],
    )[0]
    assert decoded[0].lower() == _TOKEN_IN.lower()
    assert decoded[1].lower() == _TOKEN_OUT.lower()
    assert decoded[2] == 3000
    assert decoded[3].lower() == _RECIPIENT.lower()
    assert decoded[4] == 1_777_500_000
    assert decoded[5] == 10_000_000
    assert decoded[6] == 9_900_000
    assert decoded[7] == 0  # sqrtPriceLimitX96


def test_default_fee_tier_falls_through_from_executor() -> None:
    # Constructed with pool_fee_bps=500; no per-call override.
    data = _executor_v3().build_uniswap_v3_calldata(
        token_in=_TOKEN_IN,
        token_out=_TOKEN_OUT,
        recipient=_RECIPIENT,
        amount_in=1,
        amount_out_minimum=0,
        deadline_unix=0,
    )
    decoded = abi_decode(
        ["(address,address,uint24,address,uint256,uint256,uint256,uint160)"],
        data[4:],
    )[0]
    assert decoded[2] == 500


def test_build_plan_picks_uniswap_path_when_venue_is_v3() -> None:
    plan = _executor_v3().build_plan(
        proof=b"\x00" * 256,
        public_inputs=[1, 2, 3],
        token_in=_TOKEN_IN,
        token_out=_TOKEN_OUT,
        amount_in=1_000_000,
        min_amount_out=990_000,
        deadline_unix=1_777_500_000,
    )
    assert len(plan.trades) == 1
    selector = plan.trades[0].data[:4]
    expected = keccak(
        b"exactInputSingle((address,address,uint24,address,uint256,uint256,uint256,uint160))"
    )[:4]
    assert selector == expected


def test_build_plan_picks_algebra_path_by_default() -> None:
    algebra_executor = TradeExecutor(
        rpc_url="",
        operator_pk="",
        strategy_vault_address="",
        mock_router_address="0x55782e7019f4619a06a25bf66d2998c8fe2cc436",
        chain_id=2368,
    )
    plan = algebra_executor.build_plan(
        proof=b"\x00" * 256,
        public_inputs=[1, 2, 3],
        token_in=_TOKEN_IN,
        token_out=_TOKEN_OUT,
        amount_in=1_000_000,
        min_amount_out=990_000,
        deadline_unix=1_777_500_000,
    )
    selector = plan.trades[0].data[:4]
    expected = keccak(
        b"exactInputSingle((address,address,address,uint256,uint256,uint256,uint160))"
    )[:4]
    assert selector == expected
