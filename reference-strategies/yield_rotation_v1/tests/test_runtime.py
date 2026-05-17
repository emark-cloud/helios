"""Runtime happy-path tests for `YieldRotationRuntime`.

Single-tick scenarios with fake oracle / prover / executor — verifies
the strategy → witness → prover → executor wiring is intact and that
stats counters increment as expected.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from yield_rotation_v1.executor import ExecutionRecord, TradeExecutor
from yield_rotation_v1.prover_client import ProofResult, ProverDegraded
from yield_rotation_v1.runtime import RuntimeConfig, YieldRotationRuntime
from yield_rotation_v1.strategy import YieldRotationStrategy
from yield_rotation_v1.types import YieldTick


class _FakeOracle:
    """Returns canned `YieldTick`s. `aclose` no-op."""

    def __init__(self, ticks: dict[int, YieldTick]) -> None:
        self._ticks = ticks

    async def fetch_latest_tick(self, market_id: str, registry_id: int) -> YieldTick | None:
        del market_id
        return self._ticks.get(registry_id)

    async def aclose(self) -> None:
        return None


class _FakeProver:
    """Returns a stable proof result. `degrade=True` raises `ProverDegraded`."""

    def __init__(self, *, degrade: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self._degrade = degrade

    async def prove(self, *, strategy_class: str, witness_inputs: dict[str, Any]) -> ProofResult:
        self.calls.append({"class": strategy_class, "inputs": witness_inputs})
        if self._degrade:
            raise ProverDegraded("prover degraded")
        return ProofResult(
            proof={
                "pi_a": ["1", "2", "1"],
                "pi_b": [["3", "4"], ["5", "6"]],
                "pi_c": ["7", "8", "1"],
            },
            public_signals=[str(witness_inputs["trade_hash"])] + ["0"] * 8,
        )

    async def aclose(self) -> None:
        return None


def _make_runtime(
    *,
    ticks: dict[int, YieldTick],
    degrade_prover: bool = False,
) -> tuple[YieldRotationRuntime, _FakeProver, TradeExecutor]:
    strategy = YieldRotationStrategy(
        allowlisted_markets=(1, 2),
        signal_threshold_bps=80,
        bridging_cost_bps=30,
    )
    strategy.set_capital(10_000)
    strategy.set_active_market(1)

    executor = TradeExecutor(
        rpc_url="",
        operator_pk="",
        strategy_vault_address="",  # ⇒ dry-run mode
        chain_id=2368,
    )
    prover = _FakeProver(degrade=degrade_prover)
    runtime = YieldRotationRuntime(
        strategy=strategy,
        oracle=_FakeOracle(ticks),  # type: ignore[arg-type]
        prover=prover,  # type: ignore[arg-type]
        executor=executor,
        config=RuntimeConfig(declared_class_field=0x9ABC),
        market_subscriptions=[("AAVE_USDC", 1), ("COMPOUND_USDC", 2)],
    )
    return runtime, prover, executor


@pytest.mark.asyncio
async def test_tick_yield_rotates_on_threshold_breach() -> None:
    ticks = {
        1: YieldTick(market_id=1, apy_bps_e6=420 * 1_000_000, timestamp_ms=1),
        2: YieldTick(market_id=2, apy_bps_e6=550 * 1_000_000, timestamp_ms=1),
    }
    runtime, prover, executor = _make_runtime(ticks=ticks)
    record = await runtime.tick_yield()
    assert isinstance(record, ExecutionRecord)
    assert runtime.stats.ticks_observed == 1
    assert runtime.stats.signals_fired == 1
    assert runtime.stats.proofs_generated == 1
    assert runtime.stats.execs_submitted == 1
    assert len(executor.pending) == 1
    # Active market should have flipped to the destination.
    assert runtime.stats.last_signal["m_from"] == 1
    assert runtime.stats.last_signal["m_to"] == 2
    # Prover saw the right class.
    assert prover.calls[0]["class"] == "yield_rotation_v1"


@pytest.mark.asyncio
async def test_tick_yield_holds_when_below_threshold() -> None:
    ticks = {
        1: YieldTick(market_id=1, apy_bps_e6=420 * 1_000_000, timestamp_ms=1),
        2: YieldTick(market_id=2, apy_bps_e6=525 * 1_000_000, timestamp_ms=1),
    }
    runtime, prover, executor = _make_runtime(ticks=ticks)
    record = await runtime.tick_yield()
    assert record is None
    assert runtime.stats.signals_fired == 0
    assert runtime.stats.proofs_generated == 0
    assert len(executor.pending) == 0
    assert prover.calls == []


@pytest.mark.asyncio
async def test_tick_yield_records_prover_degraded_failure() -> None:
    ticks = {
        1: YieldTick(market_id=1, apy_bps_e6=420 * 1_000_000, timestamp_ms=1),
        2: YieldTick(market_id=2, apy_bps_e6=550 * 1_000_000, timestamp_ms=1),
    }
    runtime, _prover, executor = _make_runtime(ticks=ticks, degrade_prover=True)
    record = await runtime.tick_yield()
    assert record is None
    assert runtime.stats.signals_fired == 1
    assert runtime.stats.proof_failures == 1
    assert runtime.stats.proofs_generated == 0
    assert len(executor.pending) == 0
    assert "degraded" in runtime.stats.last_error.lower()


@pytest.mark.asyncio
async def test_unfundable_rotation_caught_not_crash() -> None:
    """`RotationIntent` int-coerces `amount_in_usd` and rejects `<= 0`
    *at construction* (helios/types.py), so an under-funded yr vault
    surfaces as a sub-$1 rotation that raises inside `on_yield_tick` —
    before any witness/proof. Without the runtime guard that ValueError
    propagates out of `_tick_loop` and kills the tick loop. It must
    instead be recorded as `signals_unfundable` (never `proof_failures`),
    the prover never called, and the loop must survive. Mirrors the live
    Kite under-funding scale (~2.86e-13 mUSDC NAV)."""
    ticks = {
        1: YieldTick(market_id=1, apy_bps_e6=420 * 1_000_000, timestamp_ms=1),
        2: YieldTick(market_id=2, apy_bps_e6=550 * 1_000_000, timestamp_ms=1),
    }
    runtime, prover, executor = _make_runtime(ticks=ticks)
    runtime._strategy.set_capital(2.86e-13)  # the actual seeded-NAV scale on Kite

    record = await runtime.tick_yield()  # must NOT raise

    assert record is None
    assert runtime.stats.signals_fired == 1
    assert runtime.stats.signals_unfundable == 1
    assert runtime.stats.proof_failures == 0
    assert runtime.stats.proofs_generated == 0
    assert len(executor.pending) == 0
    assert prover.calls == [], "prover must not be called for an unfundable rotation"
    assert "under-funded" in runtime.stats.last_error


@pytest.mark.asyncio
async def test_tick_yield_no_op_when_oracle_returns_nothing() -> None:
    runtime, _prover, executor = _make_runtime(ticks={})
    record = await runtime.tick_yield()
    assert record is None
    assert runtime.stats.ticks_observed == 0
    assert len(executor.pending) == 0


@pytest.mark.asyncio
async def test_runtime_requires_subscriptions() -> None:
    strategy = YieldRotationStrategy(allowlisted_markets=(1, 2))
    executor = TradeExecutor(rpc_url="", operator_pk="", strategy_vault_address="", chain_id=2368)
    with pytest.raises(ValueError, match="market_subscriptions"):
        YieldRotationRuntime(
            strategy=strategy,
            oracle=_FakeOracle({}),  # type: ignore[arg-type]
            prover=_FakeProver(),  # type: ignore[arg-type]
            executor=executor,
            config=RuntimeConfig(),
            market_subscriptions=[],
        )


@pytest.mark.asyncio
async def test_lifecycle_start_then_stop_is_clean() -> None:
    runtime, _prover, _executor = _make_runtime(ticks={})
    runtime.start()
    # Let the first scheduled tick run, then immediately stop.
    await asyncio.sleep(0)
    await runtime.stop()
    # idempotent stop
    await runtime.stop()


# ── NAV seed from chain (yr reportNAV Panic 0x11 root-cause fix) ──
class _Call:
    def __init__(self, v: Any) -> None:
        self._v = v

    def call(self) -> Any:
        if isinstance(self._v, Exception):
            raise self._v
        return self._v


class _FakeFns:
    def __init__(self, m: dict[str, Any]) -> None:
        self._m = m

    def baseAsset(self) -> _Call:  # ERC20/vault ABI name
        return _Call(self._m["baseAsset"])

    def decimals(self) -> _Call:
        return _Call(self._m["decimals"])

    def balanceOf(self, _a: str) -> _Call:  # ERC20 ABI name
        return _Call(self._m["balanceOf"])


class _FakeW3:
    def __init__(self, m: dict[str, Any]) -> None:
        self._m = m
        self.eth = self

    def contract(self, *, address: str, abi: Any) -> Any:
        del address, abi
        outer = self

        class _C:
            functions = _FakeFns(outer._m)

        return _C()

    @staticmethod
    def to_checksum_address(a: str) -> str:
        return a


class _LiveStubExecutor:
    chain_id = 2368
    vault = "0x" + "ee" * 20

    def __init__(self, w3: Any, *, live: bool = True) -> None:
        self.w3 = w3
        self.live = live


def _yr_rt(stub: Any) -> YieldRotationRuntime:
    strategy = YieldRotationStrategy(
        allowlisted_markets=(1, 2), signal_threshold_bps=80, bridging_cost_bps=30
    )
    strategy.set_capital(10_000)  # seeds nav=10_000 as the prior last-good
    return YieldRotationRuntime(
        strategy=strategy,
        oracle=_FakeOracle({}),  # type: ignore[arg-type]
        prover=_FakeProver(),  # type: ignore[arg-type]
        executor=stub,
        config=RuntimeConfig(declared_class_field=0x9ABC),
        market_subscriptions=[("AAVE_USDC", 1), ("COMPOUND_USDC", 2)],
    )


def test_seed_nav_from_chain_sets_nav_to_onchain_balance() -> None:
    """yr must report NAV from the vault's on-chain base-asset balance,
    not strategy.nav≈0. 383 mUSDC @ 18-dec ⇒ strategy.nav = 383.0 so
    reportNAV lands at the cash floor (no NAV-divergence breach)."""
    w3 = _FakeW3({"baseAsset": "0x" + "ab" * 20, "decimals": 18, "balanceOf": 383 * 10**18})
    rt = _yr_rt(_LiveStubExecutor(w3))
    seeded = rt._seed_nav_from_chain()
    assert seeded == 383.0
    assert rt._strategy.nav == 383.0
    assert rt.stats.last_seeded_nav_usd == 383.0


def test_seed_nav_from_chain_none_on_read_failure_preserves_nav() -> None:
    """A flaky on-chain read must not post a stale/zero NAV: return None
    (caller defers the report) and leave the last-good nav untouched."""
    w3 = _FakeW3(
        {"baseAsset": "0x" + "ab" * 20, "decimals": 18, "balanceOf": RuntimeError("rpc down")}
    )
    rt = _yr_rt(_LiveStubExecutor(w3))
    rt._strategy._set_nav(1750.0)  # last-good MTM from a prior healthy tick
    assert rt._seed_nav_from_chain() is None
    assert rt._strategy.nav == 1750.0  # last-good preserved, not clobbered
    assert rt.stats.nav_seed_failures == 1


def test_seed_nav_from_chain_none_when_not_live() -> None:
    """Dry-run (executor.live False) ⇒ no seed, returns None so the nav
    loop keeps its existing dry-run behaviour."""
    rt = _yr_rt(_LiveStubExecutor(_FakeW3({}), live=False))
    assert rt._seed_nav_from_chain() is None


def _nav_rt(*, asset_decimals: dict[str, int] | None) -> YieldRotationRuntime:
    strategy = YieldRotationStrategy(
        allowlisted_markets=(1, 2), signal_threshold_bps=80, bridging_cost_bps=30
    )
    strategy.set_capital(10_000)
    executor = TradeExecutor(
        rpc_url="",  # ⇒ dry-run; submit_nav echoes total_nav_e18 into extras
        operator_pk="",
        strategy_vault_address="0x" + "ab" * 20,  # placeholder for NAV signing
        chain_id=2368,
    )
    return YieldRotationRuntime(
        strategy=strategy,
        oracle=_FakeOracle({}),  # type: ignore[arg-type]
        prover=_FakeProver(),  # type: ignore[arg-type]
        executor=executor,
        config=RuntimeConfig(declared_class_field=0x9ABC, asset_decimals=asset_decimals),
        market_subscriptions=[("AAVE_USDC", 1), ("COMPOUND_USDC", 2)],
        nav_oracle_pk="0x" + "33" * 32,
    )


def test_tick_nav_scales_by_base_decimals_when_configured() -> None:
    """Arb mUSDC is 6-dec. NAV must be reported in native units so it
    compares against the vault's 6-dec maxCapacity — eeb1326 fixed
    mom/mr but skipped yr, so yr.arb reverted NavExceedsCap every tick."""
    rt = _nav_rt(asset_decimals={"USDC": 6})
    record = rt.tick_nav(10_000.0, timestamp=1_700_000_000)
    assert record.extras["total_nav_e18"] == 10_000 * 10**6


def test_tick_nav_defaults_to_18_decimals() -> None:
    """No asset_decimals (Kite default) ⇒ legacy 1e18 encoding, bit-for-bit."""
    rt = _nav_rt(asset_decimals=None)
    record = rt.tick_nav(10_000.0, timestamp=1_700_000_000)
    assert record.extras["total_nav_e18"] == 10_000 * 10**18
