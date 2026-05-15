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
