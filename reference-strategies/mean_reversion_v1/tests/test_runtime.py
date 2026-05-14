"""End-to-end runtime tick: stub oracle → strategy → stub prover → executor."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_keys.datatypes import Signature
from helios.types import MarketSnapshot
from mean_reversion_v1.executor import TradeExecutor
from mean_reversion_v1.oracle_client import (
    OracleClient,
    OracleEmptyError,
    SignedSnapshot,
    SnapshotBundle,
)
from mean_reversion_v1.prover_client import ProofResult, ProverClient, ProverDegraded
from mean_reversion_v1.runtime import MeanReversionRuntime, RuntimeConfig
from mean_reversion_v1.strategy import LOOKBACK_BARS, MeanReversionStrategy


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
        return ProofResult(
            proof={
                "pi_a": ["1", "2", "1"],
                "pi_b": [["3", "4"], ["5", "6"], ["1", "0"]],
                "pi_c": ["7", "8", "1"],
                "protocol": "groth16",
            },
            # Mirrors the 14-PI layout (mean_reversion shares momentum's PI shape).
            public_signals=[
                "1234",  # trade_hash placeholder
                str(int(witness_inputs["declared_class"])),
                str(int(witness_inputs["strategy_vault"])),
                "0",  # params_hash placeholder
                str(int(witness_inputs["allocator_address"])),
                str(int(witness_inputs["asset_in_idx"])),
                str(int(witness_inputs["asset_out_idx"])),
                str(int(witness_inputs["amount_in"])),
                str(int(witness_inputs["min_amount_out"])),
                str(int(witness_inputs["trade_direction"])),
                str(int(witness_inputs["nonce"])),
                str(int(witness_inputs["block_window_start"])),
                str(int(witness_inputs["block_window_end"])),
                "0",  # oracle_root placeholder
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
) -> tuple[MeanReversionRuntime, _StubProver]:
    strategy = MeanReversionStrategy(n_sigma_x100=200)
    strategy.set_capital(10_000)
    oracle = _StubOracle(prices_per_asset)
    prover = _StubProver(**kwargs)
    rt = MeanReversionRuntime(
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


def _dip_prices() -> list[int]:
    """16 bars: 15 × $1000, last $700 — replicates gen-fixture-mr.js."""
    return [(1000 * 10**18)] * (LOOKBACK_BARS - 1) + [(700 * 10**18)]


def _flat_prices() -> list[int]:
    return [(1000 * 10**18)] * LOOKBACK_BARS


@pytest.mark.asyncio
async def test_signal_fires_proof_and_executes() -> None:
    rt, prover = _runtime({"WETH": _dip_prices()})

    records = await rt.tick_bar()
    assert len(records) == 1
    assert rt.stats.signals_fired == 1
    assert rt.stats.proofs_generated == 1
    assert rt.stats.execs_submitted == 1
    assert prover.calls[0]["class"] == "mean_reversion_v1"
    inputs = prover.calls[0]["inputs"]
    assert inputs["is_long_entry"] == "1"
    assert inputs["signal_threshold"] == "200"
    assert int(inputs["amount_in"]) > 0


@pytest.mark.asyncio
async def test_no_signal_no_call() -> None:
    rt, prover = _runtime({"WETH": _flat_prices()})
    records = await rt.tick_bar()
    assert records == []
    assert rt.stats.signals_fired == 0
    assert prover.calls == []


@pytest.mark.asyncio
async def test_prover_degraded_records_failure() -> None:
    rt, _ = _runtime({"WETH": _dip_prices()}, raise_degraded=True)
    records = await rt.tick_bar()
    assert records == []
    assert rt.stats.signals_fired == 1
    assert rt.stats.proof_failures == 1
    assert rt.stats.last_error == "stub"


@pytest.mark.asyncio
async def test_oracle_empty_skips_silently() -> None:
    rt, _ = _runtime({})
    records = await rt.tick_bar()
    assert records == []
    assert rt.stats.signals_fired == 0


@pytest.mark.asyncio
async def test_dry_run_executor_records_pending() -> None:
    rt, _ = _runtime({"WETH": _dip_prices()})
    await rt.tick_bar()
    assert len(rt.records) == 1
    record = rt.records[0]
    assert not record.submitted  # address-gated dry run
    assert record.extras["asset"] == "WETH"
    assert len(record.plan.public_inputs) == 14


def test_nav_signing_round_trip() -> None:
    """NAV signature must recover to the configured nav_oracle key
    against StrategyVault's EIP-712 `NAVUpdate(uint256 totalNAV, uint64
    timestamp)` digest under domain `(HeliosStrategyVault, "1", chainId,
    verifyingContract=vault)`."""
    nav_pk = "0x" + "33" * 32
    nav_addr = Account.from_key(nav_pk).address

    strategy = MeanReversionStrategy()
    strategy.set_capital(10_000)
    executor = TradeExecutor(
        rpc_url="",
        operator_pk="",
        strategy_vault_address="0x" + "ab" * 20,
        mock_router_address="0x" + "cd" * 20,
        chain_id=2368,
    )
    rt = MeanReversionRuntime(
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
    sig_for_recover = signature[:64] + bytes([signature[64] - 27])
    recovered_pubkey = Signature(signature_bytes=sig_for_recover).recover_public_key_from_msg_hash(
        expected.message_hash
    )
    assert recovered_pubkey.to_checksum_address() == nav_addr


# ── Phase-6 multi-asset wiring ─────────────────────────────────


@pytest.mark.asyncio
async def test_runtime_threads_asset_decimals_into_witness() -> None:
    """RuntimeConfig.asset_decimals must reach the witness builder.
    A z-score dip on WETH fires LONG (USDC -> WETH) — with USDC=6
    raw decimals, $1000 of mUSDC becomes 10^9 raw, not 10^21."""
    rt, prover = _runtime({"WETH": _dip_prices()})
    rt._cfg = RuntimeConfig(  # type: ignore[attr-defined]
        bar_interval_sec=60,
        nav_interval_sec=300,
        block_window_size=50,
        declared_class_field=0xABC,
        asset_decimals={"USDC": 6, "WETH": 18},
    )
    # Drop NAV so _size() returns a deterministic $1000 (default fraction
    # is 0.5 — at NAV=2000 that yields 1000 USDC, which under USDC=6 dec
    # is exactly 10^9 raw).
    rt._strategy.set_capital(2_000)
    await rt.tick_bar()
    assert prover.calls, "expected a prover request"
    inputs = prover.calls[0]["inputs"]
    assert int(inputs["amount_in"]) == 1_000 * 10**6


def test_parse_asset_decimals_helper() -> None:
    from mean_reversion_v1.service import _parse_asset_decimals

    assert _parse_asset_decimals("") is None
    assert _parse_asset_decimals('{"USDC":6,"WETH":18}') == {"USDC": 6, "WETH": 18}

    import pytest as _pt

    with _pt.raises(ValueError):
        _parse_asset_decimals("[1,2,3]")
    with _pt.raises(ValueError):
        _parse_asset_decimals('{"USDC":-1}')


# ── Lockstep guard: symbols and addresses must align by index ──
def test_runtime_rejects_symbol_address_lockstep_violation() -> None:
    """Base mr ships a 2-symbol strategy override + 2-real-address +
    6-empty padding. The lockstep guard must catch the inverse case
    where the 4-symbol default strategy is paired with a 2-address
    universe — left unchecked, this silently routes WBTC signals to
    WETH9's address slot."""
    strategy = MeanReversionStrategy(n_sigma_x100=200)  # 4-symbol default
    base_2 = ["0x" + "ab" * 20, "0x" + "cd" * 20] + [""] * 6  # only 2 real
    with pytest.raises(ValueError, match="lockstep"):
        MeanReversionRuntime(
            strategy=strategy,
            oracle=_StubOracle({}),
            prover=_StubProver(),
            executor=_executor(),
            config=RuntimeConfig(
                bar_interval_sec=60, nav_interval_sec=300, declared_class_field=0xABC
            ),
            allocator_address="0x" + "11" * 20,
            asset_universe_addresses=base_2,
        )


def test_runtime_accepts_aligned_2_asset_universe() -> None:
    """The matching shape — Base-style 2-symbol strategy + 2-real-address
    + 6-empty padding — must construct cleanly so the production Base
    deploy path works."""
    strategy = MeanReversionStrategy(n_sigma_x100=200, asset_universe=("USDC", "WETH"))
    base_2 = ["0x" + "ab" * 20, "0x" + "cd" * 20] + [""] * 6
    rt = MeanReversionRuntime(
        strategy=strategy,
        oracle=_StubOracle({}),
        prover=_StubProver(),
        executor=_executor(),
        config=RuntimeConfig(
            bar_interval_sec=60, nav_interval_sec=300, declared_class_field=0xABC
        ),
        allocator_address="0x" + "11" * 20,
        asset_universe_addresses=base_2,
    )
    assert rt is not None
