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
from momentum_v1.oracle_client import (
    OracleClient,
    OracleCommitError,
    OracleEmptyError,
    SignedSnapshot,
    SnapshotBundle,
)
from momentum_v1.prover_client import ProofResult, ProverClient, ProverDegraded
from momentum_v1.runtime import MomentumRuntime, RuntimeConfig
from momentum_v1.strategy import MomentumStrategy


class _StubOracle(OracleClient):
    def __init__(
        self, prices_per_asset: dict[str, list[int]], *, commit_fails: bool = False
    ) -> None:
        self._prices = prices_per_asset
        self._commit_fails = commit_fails
        self.commit_calls: list[str] = []
        self.fetch_calls: list[str] = []

    async def request_commit(self, asset: str) -> dict[str, Any]:  # type: ignore[override]
        self.commit_calls.append(asset)
        if self._commit_fails:
            raise OracleCommitError("stub commit failure")
        return {"asset": asset, "committed": True}

    async def fetch_recent(self, asset: str, n: int) -> SnapshotBundle:  # type: ignore[override]
        self.fetch_calls.append(asset)
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
                # 14 PIs in `momentum_v1.circom` order — mirrors the
                # production prover output. Values come from the
                # witness so test assertions on `executeWithProof`
                # arguments stay deterministic.
                str(int(witness_inputs["trade_hash"])),
                str(int(witness_inputs["declared_class"])),
                str(int(witness_inputs["strategy_vault"])),
                str(int(witness_inputs["params_hash"])),
                str(int(witness_inputs["allocator_address"])),
                str(int(witness_inputs["asset_in_idx"])),
                str(int(witness_inputs["asset_out_idx"])),
                str(int(witness_inputs["amount_in"])),
                str(int(witness_inputs["min_amount_out"])),
                str(int(witness_inputs["trade_direction"])),
                str(int(witness_inputs["nonce"])),
                str(int(witness_inputs["block_window_start"])),
                str(int(witness_inputs["block_window_end"])),
                str(int(witness_inputs["oracle_root"])),
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
    prices_per_asset: dict[str, list[int]], *, commit_fails: bool = False, **kwargs
) -> tuple[MomentumRuntime, _StubProver]:
    strategy = MomentumStrategy(signal_threshold=0.005, lookback_bars=5)
    strategy.set_capital(10_000)
    oracle = _StubOracle(prices_per_asset, commit_fails=commit_fails)
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
async def test_signal_anchors_commit_before_proving() -> None:
    prices = [int((2000 + i * 5) * 10**18) for i in range(16)]
    rt, _ = _runtime({"WETH": prices})
    records = await rt.tick_bar()
    assert len(records) == 1
    oracle = rt._oracle
    assert isinstance(oracle, _StubOracle)
    # Commit-on-demand fired exactly once, only for the asset that
    # produced a signal (other universe assets have no prices → skipped
    # before any commit).
    assert oracle.commit_calls == ["WETH"]
    # WETH was fetched twice: tick_bar's read + the _handle_signal
    # re-fetch, so the witness proves exactly the just-committed window.
    assert oracle.fetch_calls.count("WETH") == 2
    assert rt.stats.proofs_generated == 1


@pytest.mark.asyncio
async def test_commit_failure_skips_trade_safely() -> None:
    prices = [int((2000 + i * 5) * 10**18) for i in range(16)]
    rt, prover = _runtime({"WETH": prices}, commit_fails=True)
    records = await rt.tick_bar()
    # Signal fired but the anchor commit didn't mine → safe skip, no
    # proof attempted (strictly better than an on-chain revert).
    assert records == []
    assert rt.stats.signals_fired == 1
    assert rt.stats.commit_failures == 1
    assert rt.stats.proofs_generated == 0
    assert prover.calls == []
    assert "stub commit failure" in rt.stats.last_error


@pytest.mark.asyncio
async def test_unfundable_signal_skips_prover_before_constraint0() -> None:
    """A vault too thinly funded for `amount_in` to resolve to ≥ 1 wei
    must be dropped *before* the prover: counted as `signals_unfundable`,
    never `proof_failures`, and never sent to snarkjs (where circuit
    Constraint 0 would reject it as an indistinguishable
    `prover.degraded`). Mirrors the live Kite under-funding scale —
    `int(nav·fraction · 10**6)` floors to 0 on the USDC leg."""
    prices = [int((2000 + i * 5) * 10**18) for i in range(16)]  # LONG signal
    rt, prover = _runtime({"WETH": prices})
    rt._cfg = RuntimeConfig(  # type: ignore[attr-defined]
        bar_interval_sec=60,
        nav_interval_sec=300,
        block_window_size=50,
        declared_class_field=0xABC,
        asset_decimals={"USDC": 6, "WETH": 18},
    )
    rt._strategy.set_capital(2.86e-13)  # the actual seeded-NAV scale on Kite

    records = await rt.tick_bar()

    assert records == []
    assert rt.stats.signals_fired == 1
    assert rt.stats.signals_unfundable == 1
    assert rt.stats.proof_failures == 0
    assert rt.stats.proofs_generated == 0
    assert prover.calls == [], "prover must not be called for a 0-wei amount_in"
    assert "under-funded" in rt.stats.last_error


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
    # 14 PIs match `momentum_v1.circom`'s public-input layout (PR3
    # promoted to the SDK builder; old shape was 8).
    assert len(record.plan.public_inputs) == 14


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


# ── Phase-6 multi-asset wiring ─────────────────────────────────


@pytest.mark.asyncio
async def test_runtime_threads_asset_decimals_into_witness() -> None:
    """When `RuntimeConfig.asset_decimals` is set, the witness builder
    receives it and switches to raw-tokenIn encoding. Verify by inspecting
    the prover request: $1000 of USDC at 6 decimals must hit the prover
    as 10^9 raw, not 10^21 (the legacy USD*10^18 value)."""
    prices = [int((2000 + i * 5) * 10**18) for i in range(16)]
    rt, prover = _runtime({"WETH": prices})
    rt._cfg = RuntimeConfig(  # type: ignore[attr-defined]
        bar_interval_sec=60,
        nav_interval_sec=300,
        block_window_size=50,
        declared_class_field=0xABC,
        asset_decimals={"USDC": 6, "WETH": 18},
    )
    rt._strategy.set_capital(2_000)
    await rt.tick_bar()
    assert prover.calls, "expected a prover request"
    inputs = prover.calls[0]["inputs"]
    # _size() returns NAV * 0.5 = $1000 by default; raw mUSDC@6dec → 10^9.
    assert int(inputs["amount_in"]) == 1_000 * 10**6


def test_parse_asset_decimals_helper() -> None:
    from momentum_v1.service import _parse_asset_decimals

    assert _parse_asset_decimals("") is None
    assert _parse_asset_decimals("   ") is None
    assert _parse_asset_decimals('{"USDC":6,"WETH":18}') == {"USDC": 6, "WETH": 18}

    import pytest as _pt

    with _pt.raises(ValueError):
        _parse_asset_decimals("[1,2,3]")
    with _pt.raises(ValueError):
        _parse_asset_decimals('{"USDC":-1}')
    with _pt.raises(ValueError):
        _parse_asset_decimals('{"USDC":"6"}')


# ── Lockstep guard: symbols and addresses must align by index ──
def test_runtime_rejects_symbol_address_lockstep_violation() -> None:
    strategy = MomentumStrategy(signal_threshold=0.005, lookback_bars=5)  # 4-symbol default
    base_2 = ["0x" + "ab" * 20, "0x" + "cd" * 20] + [""] * 6
    with pytest.raises(ValueError, match="lockstep"):
        MomentumRuntime(
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
    strategy = MomentumStrategy(
        signal_threshold=0.005, lookback_bars=5, asset_universe=("USDC", "WETH")
    )
    base_2 = ["0x" + "ab" * 20, "0x" + "cd" * 20] + [""] * 6
    rt = MomentumRuntime(
        strategy=strategy,
        oracle=_StubOracle({}),
        prover=_StubProver(),
        executor=_executor(),
        config=RuntimeConfig(bar_interval_sec=60, nav_interval_sec=300, declared_class_field=0xABC),
        allocator_address="0x" + "11" * 20,
        asset_universe_addresses=base_2,
    )
    assert rt is not None
