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


# ── Position-aware NAV + position-book sync from chain (A+B) ────
from momentum_v1.executor import ExecutionPlan, ExecutionRecord  # noqa: E402


class _LiveTradeExecutor(TradeExecutor):
    """Live executor (live=True) whose `submit` does not dial out.
    `build_plan` is the real pure calldata builder so the witness/clamp
    path is exercised end-to-end."""

    def __init__(self) -> None:
        super().__init__(
            rpc_url="http://stub",
            operator_pk="0x" + "11" * 32,
            strategy_vault_address="0x" + "ee" * 20,
            mock_router_address="0x" + "ab" * 20,
            chain_id=2368,
        )
        self._w3 = object()  # balanceOf is monkeypatched; never dialled

    def submit(self, plan: ExecutionPlan, **extras: Any) -> ExecutionRecord:
        return ExecutionRecord(plan=plan, submitted=False, extras=dict(extras))


def _rising() -> list[int]:
    """~0.4%/bar up — recent_return over 5 bars beats the 0.5% threshold."""
    return [int((2000 + i * 5) * 10**18) for i in range(16)]


def _falling() -> list[int]:
    """~0.4%/bar down — recent_return below -0.5% ⇒ EXIT signal flip."""
    return [int((2000 - i * 5) * 10**18) for i in range(16)]


def _flat16() -> list[int]:
    return [2000 * 10**18] * 16


def _live_rt(
    monkeypatch,
    prices: dict[str, list[int]],
    *,
    balances: dict[str, int],
    asset_decimals: dict[str, int] | None = None,
) -> tuple[MomentumRuntime, _StubProver]:
    universe = [f"0x{i:040x}" for i in range(1, 9)]
    by_addr = {universe[0]: balances.get("USDC", 0), universe[2]: balances.get("WETH", 0)}

    def _bal(*, w3, token_address, holder_address) -> int:
        del w3, holder_address
        return by_addr.get(token_address, 0)

    monkeypatch.setattr("helios.runtime.nav_seed.read_erc20_balance", _bal)
    monkeypatch.setattr("momentum_v1.runtime.read_erc20_balance", _bal)

    strategy = MomentumStrategy(signal_threshold=0.005, lookback_bars=5)
    prover = _StubProver()
    rt = MomentumRuntime(
        strategy=strategy,
        oracle=_StubOracle(prices),
        prover=prover,
        executor=_LiveTradeExecutor(),
        config=RuntimeConfig(
            bar_interval_sec=60,
            nav_interval_sec=300,
            block_window_size=50,
            declared_class_field=0xABC,
            asset_decimals=asset_decimals,
        ),
        allocator_address="0x" + "11" * 20,
        asset_universe_addresses=universe,
    )
    return rt, prover


@pytest.mark.asyncio
async def test_nav_is_position_aware_when_base_drained(monkeypatch) -> None:
    """Vault holds 0 mUSDC but 2 WETH. Base-only seeding would report
    NAV ≈ 0 and size every entry to 0; position-aware NAV marks the
    held WETH to the oracle price while spendable cash stays 0."""
    rt, _ = _live_rt(
        monkeypatch,
        {"WETH": _flat16()},  # flat ⇒ no signal
        balances={"USDC": 0, "WETH": 2 * 10**18},
        asset_decimals={"USDC": 18, "WETH": 18, "WBTC": 8, "WSOL": 9},
    )

    records = await rt.tick_bar()

    assert records == []
    assert rt.stats.signals_fired == 0
    assert rt._strategy.available_capital == 0.0
    assert rt.stats.last_seeded_nav_usd == 0.0
    assert rt._strategy.nav == pytest.approx(4_000.0)  # 2 WETH @ $2000
    assert rt.stats.last_position_nav_usd == pytest.approx(4_000.0)


@pytest.mark.asyncio
async def test_rehydrated_position_exits_on_flip_and_clamps(monkeypatch) -> None:
    """The runtime never wrote the position book, so momentum could
    never EXIT the WETH it holds. Syncing the position from chain lets a
    momentum signal-flip emit an EXIT, with amount_in clamped to the
    held WETH so the sell leg can't ulp-overshoot (TradeCallFailed(1))."""
    raw = 38_609_100_195_824_967
    rt, prover = _live_rt(
        monkeypatch,
        {"WETH": _falling()},  # recent_return < -threshold ⇒ EXIT
        balances={"USDC": 0, "WETH": raw},
        asset_decimals={"USDC": 18, "WETH": 18, "WBTC": 8, "WSOL": 9},
    )

    records = await rt.tick_bar()

    assert rt.stats.signals_fired == 1
    assert len(records) == 1
    assert rt._strategy.position_for("WETH") > 0  # rehydrated from chain
    inputs = prover.calls[0]["inputs"]
    assert inputs["is_exit"] == "1"
    assert inputs["is_signal_flip"] == "1"
    assert int(inputs["asset_in_idx"]) == 2  # WETH slot
    amount_in = int(inputs["amount_in"])
    assert 1 <= amount_in <= raw  # clamped to exact on-chain balance


@pytest.mark.asyncio
async def test_long_does_not_refire_when_position_held_on_chain(monkeypatch) -> None:
    """The cash-drain root cause: with no position write-back the LONG
    guard (position <= 0) was always true, so positive momentum re-bought
    every bar until empty. Syncing the held WETH stops it."""
    rt, prover = _live_rt(
        monkeypatch,
        {"WETH": _rising()},  # LONG signal every bar
        balances={"USDC": 0, "WETH": 2 * 10**18},  # already long
        asset_decimals={"USDC": 18, "WETH": 18},
    )

    records = await rt.tick_bar()

    assert rt._strategy.position_for("WETH") > 0
    assert rt.stats.signals_fired == 0  # no re-LONG
    assert prover.calls == []
    assert records == []


@pytest.mark.asyncio
async def test_subdust_holding_is_not_a_position(monkeypatch) -> None:
    """A few wei of residue must not block a legitimate re-entry: below
    the dust floor momentum is flat and the LONG fires."""
    rt, prover = _live_rt(
        monkeypatch,
        {"WETH": _rising()},
        balances={"USDC": 5_000 * 10**18, "WETH": 11},  # 11 wei ≈ $0 ≪ $1
        asset_decimals={"USDC": 18, "WETH": 18},
    )
    rt._strategy._set_nav(5_000.0)  # warmed runtime (NAV set end-of-bar)

    records = await rt.tick_bar()

    assert rt._strategy.position_for("WETH") == 0.0  # dust ≠ position
    assert rt.stats.signals_fired == 1
    assert len(records) == 1
    assert prover.calls[0]["inputs"]["is_long_entry"] == "1"


@pytest.mark.asyncio
async def test_no_position_sync_in_dry_run(monkeypatch) -> None:
    """Sync is gated on executor.live: a dry-run runtime must not
    rehydrate (existing dry-run behaviour preserved)."""
    universe = [f"0x{i:040x}" for i in range(1, 9)]

    def _bal(*, w3, token_address, holder_address) -> int:
        del w3, token_address, holder_address
        return 2 * 10**18

    monkeypatch.setattr("momentum_v1.runtime.read_erc20_balance", _bal)
    monkeypatch.setattr("helios.runtime.nav_seed.read_erc20_balance", _bal)

    strategy = MomentumStrategy(signal_threshold=0.005, lookback_bars=5)
    strategy.set_capital(10_000)
    rt = MomentumRuntime(
        strategy=strategy,
        oracle=_StubOracle({"WETH": _falling()}),
        prover=_StubProver(),
        executor=_executor(),  # rpc_url="" ⇒ live=False
        config=RuntimeConfig(bar_interval_sec=60, nav_interval_sec=300, declared_class_field=0xABC),
        allocator_address="0x" + "11" * 20,
        asset_universe_addresses=universe,
    )
    records = await rt.tick_bar()

    assert rt._strategy.position_for("WETH") == 0.0  # no sync when not live
    assert rt.stats.signals_fired == 0
    assert records == []


@pytest.mark.asyncio
async def test_failed_base_seed_does_not_post_zero_on_cash_only_vault(monkeypatch) -> None:
    """The live frontend-PnL bug (phase6VaultMomentum): a cash-only
    vault whose base-cash seed transiently fails (flaky RPC) must NOT
    post NAV=0 just because the zero-balance reads of non-base assets it
    doesn't hold succeed. Last-good NAV must be preserved."""
    universe = [f"0x{i:040x}" for i in range(1, 9)]
    usdc_addr = universe[0]

    def _bal(*, w3, token_address, holder_address) -> int:
        del w3, holder_address
        if token_address == usdc_addr:
            raise RuntimeError("rpc RemoteDisconnected")  # base seed fails
        return 0  # non-base reads succeed: cash-only vault holds 0 of these

    monkeypatch.setattr("helios.runtime.nav_seed.read_erc20_balance", _bal)
    monkeypatch.setattr("momentum_v1.runtime.read_erc20_balance", _bal)

    strategy = MomentumStrategy(signal_threshold=0.005, lookback_bars=5)
    strategy._set_nav(280.05)  # last-good MTM from prior healthy bars
    rt = MomentumRuntime(
        strategy=strategy,
        oracle=_StubOracle({"WETH": _flat16()}),  # flat ⇒ no signal
        prover=_StubProver(),
        executor=_LiveTradeExecutor(),
        config=RuntimeConfig(bar_interval_sec=60, nav_interval_sec=300, declared_class_field=0xABC),
        allocator_address="0x" + "11" * 20,
        asset_universe_addresses=universe,
    )

    records = await rt.tick_bar()

    assert records == []
    assert rt._strategy.nav == pytest.approx(280.05)  # last-good preserved
    assert rt.stats.last_position_nav_usd == 0.0  # never written this bar


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
