"""End-to-end runtime tick: stub oracle → strategy → stub prover → executor."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_keys.datatypes import Signature
from helios.types import MarketSnapshot
from momentum_v1.executor import TradeExecutor
from momentum_v1.oracle_client import OracleClient, OracleEmptyError, SignedSnapshot, SnapshotBundle
from momentum_v1.prover_client import ProofResult, ProverClient, ProverDegraded
from momentum_v1.runtime import MomentumRuntime, RuntimeConfig
from momentum_v1.strategy import MomentumStrategy


class _StubOracle(OracleClient):
    def __init__(self, prices_per_asset: dict[str, list[int]]) -> None:
        self._prices = prices_per_asset

    async def fetch_recent(self, asset: str, n: int) -> SnapshotBundle:  # type: ignore[override]
        prices = self._prices.get(asset)
        if not prices:
            raise OracleEmptyError(asset)
        snaps = [
            SignedSnapshot(
                asset=asset,
                price_e18=p,
                timestamp_ms=1_000_000_000_000 + i * 60_000,
                source="stub",
                digest=b"\x00" * 32,
                signature=b"\x00" * 65,
            )
            for i, p in enumerate(prices[-n:])
        ]
        market = MarketSnapshot(
            asset=asset,
            timestamp=datetime.now(UTC),
            prices=[s.price_e18 / 1e18 for s in snaps],
            bar_interval_sec=60,
        )
        return SnapshotBundle(market=market, signed=snaps, chain_root=b"\x00" * 32)

    async def aclose(self) -> None:
        return None


class _StubProver(ProverClient):
    def __init__(self, *, raise_degraded: bool = False) -> None:
        self.raise_degraded = raise_degraded
        self.calls: list[dict[str, Any]] = []

    async def prove(self, *, strategy_class: str, witness_inputs: dict[str, Any]) -> ProofResult:  # type: ignore[override]
        self.calls.append({"class": strategy_class, "inputs": witness_inputs})
        if self.raise_degraded:
            raise ProverDegraded("stub")
        # Fake but well-shaped Groth16 proof — 8 uint256 words.
        return ProofResult(
            proof={
                "pi_a": ["1", "2", "1"],
                "pi_b": [["3", "4"], ["5", "6"], ["1", "0"]],
                "pi_c": ["7", "8", "1"],
                "protocol": "groth16",
            },
            public_signals=[
                str(int(witness_inputs["asset_in"])),
                str(int(witness_inputs["asset_out"])),
                str(int(witness_inputs["amount_in"])),
                str(int(witness_inputs["min_amount_out"])),
                str(int(witness_inputs["trade_direction"])),
                str(int(witness_inputs["block_window_start"])),
                str(int(witness_inputs["block_window_end"])),
                "1234",  # placeholder trade_hash
            ],
        )

    async def aclose(self) -> None:
        return None


def _executor() -> TradeExecutor:
    return TradeExecutor(
        rpc_url="",
        operator_pk="",
        strategy_vault_address="",
        mock_router_address="0x" + "ab" * 20,
        chain_id=2368,
    )


def _runtime(
    prices_per_asset: dict[str, list[int]], **kwargs
) -> tuple[MomentumRuntime, _StubProver]:
    strategy = MomentumStrategy(signal_threshold=0.005, lookback_bars=5)
    strategy.set_capital(10_000)
    oracle = _StubOracle(prices_per_asset)
    prover = _StubProver(**kwargs)
    rt = MomentumRuntime(
        strategy=strategy,
        oracle=oracle,
        prover=prover,
        executor=_executor(),
        config=RuntimeConfig(
            bar_interval_sec=60,
            nav_interval_sec=300,
            block_window_size=50,
            declared_class_field=0xABC,
        ),
        allocator_address="0x" + "11" * 20,
        asset_universe_addresses=[f"0x{i:040x}" for i in range(1, 9)],
    )
    return rt, prover


@pytest.mark.asyncio
async def test_signal_fires_proof_and_executes() -> None:
    # 1% rise across 5 bars beats threshold of 0.5%.
    prices = [int((2000 + i * 5) * 10**18) for i in range(16)]  # ~0.4%/bar — 1.5% over 5 bars
    rt, prover = _runtime({"WETH": prices})

    records = await rt.tick_bar()
    assert len(records) == 1
    assert rt.stats.signals_fired == 1
    assert rt.stats.proofs_generated == 1
    assert rt.stats.execs_submitted == 1
    # Witness shape: prover saw a momentum_v1 request.
    assert prover.calls[0]["class"] == "momentum_v1"
    inputs = prover.calls[0]["inputs"]
    assert inputs["is_long_entry"] == "1"
    assert int(inputs["amount_in"]) > 0


@pytest.mark.asyncio
async def test_no_signal_no_call() -> None:
    # Flat prices.
    prices = [2000 * 10**18] * 16
    rt, prover = _runtime({"WETH": prices})
    records = await rt.tick_bar()
    assert records == []
    assert rt.stats.signals_fired == 0
    assert prover.calls == []


@pytest.mark.asyncio
async def test_prover_degraded_records_failure() -> None:
    prices = [int((2000 + i * 5) * 10**18) for i in range(16)]  # ~0.4%/bar — 1.5% over 5 bars
    rt, _ = _runtime({"WETH": prices}, raise_degraded=True)
    records = await rt.tick_bar()
    assert records == []
    assert rt.stats.signals_fired == 1
    assert rt.stats.proof_failures == 1
    assert rt.stats.last_error == "stub"


@pytest.mark.asyncio
async def test_oracle_empty_skips_silently() -> None:
    rt, _ = _runtime({})  # no prices for any asset
    records = await rt.tick_bar()
    assert records == []
    assert rt.stats.signals_fired == 0


@pytest.mark.asyncio
async def test_dry_run_executor_records_pending() -> None:
    prices = [int((2000 + i * 5) * 10**18) for i in range(16)]  # ~0.4%/bar — 1.5% over 5 bars
    rt, _ = _runtime({"WETH": prices})
    await rt.tick_bar()
    assert len(rt.records) == 1
    record = rt.records[0]
    assert not record.submitted  # address-gated dry run
    assert record.extras["asset"] == "WETH"
    assert len(record.plan.public_inputs) == 8


def test_nav_signing_round_trip() -> None:
    """NAV signature must recover to the configured nav_oracle key
    against StrategyVault's EIP-712 `NAVUpdate(uint256 totalNAV, uint64
    timestamp)` digest under domain `(HeliosStrategyVault, "1", chainId,
    verifyingContract=vault)`."""
    nav_pk = "0x" + "33" * 32
    nav_addr = Account.from_key(nav_pk).address

    strategy = MomentumStrategy()
    strategy.set_capital(10_000)
    executor = TradeExecutor(
        rpc_url="",
        operator_pk="",
        strategy_vault_address="0x" + "ab" * 20,
        mock_router_address="0x" + "cd" * 20,
        chain_id=2368,
    )
    rt = MomentumRuntime(
        strategy=strategy,
        oracle=_StubOracle({}),
        prover=_StubProver(),
        executor=executor,
        config=RuntimeConfig(),
        nav_oracle_pk=nav_pk,
        asset_universe_addresses=[f"0x{i:040x}" for i in range(1, 9)],
    )
    record = rt.tick_nav(10_000.0, timestamp=1_700_000_000)
    sig_hex = record.extras["signature_hex"]
    signature = bytes.fromhex(sig_hex)

    # Reproduce the StrategyVault.reportNAV EIP-712 envelope and confirm
    # that signing the same typed-data payload with the same key yields
    # the exact bytes we submitted, and that recovery returns navOracle.
    domain = {
        "name": "HeliosStrategyVault",
        "version": "1",
        "chainId": 2368,
        "verifyingContract": executor.vault,
    }
    types = {
        "NAVUpdate": [
            {"name": "totalNAV", "type": "uint256"},
            {"name": "timestamp", "type": "uint64"},
        ]
    }
    message = {"totalNAV": 10_000 * 10**18, "timestamp": 1_700_000_000}
    encoded = encode_typed_data(domain_data=domain, message_types=types, message_data=message)
    expected = Account.from_key(nav_pk).sign_message(encoded)
    assert signature == bytes(expected.signature)
    assert Account.recover_message(encoded, signature=signature) == nav_addr
    # Sanity: Signature recovery on the underlying typed-data digest returns
    # the same address (eth_account.sign_message produces v ∈ {27,28}).
    sig_for_recover = signature[:64] + bytes([signature[64] - 27])
    recovered_pubkey = Signature(signature_bytes=sig_for_recover).recover_public_key_from_msg_hash(
        expected.message_hash
    )
    assert recovered_pubkey.to_checksum_address() == nav_addr
