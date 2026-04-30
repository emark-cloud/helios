"""Runtime that drives the reference yield_rotation_v1 strategy.

Two async cadences:
  * `yield_interval_sec` — pull the latest signed APY snapshot per
    allowlisted market, run `on_yield_tick`, and (on a positive
    `RotationIntent`) build the witness, generate the Groth16 proof,
    submit `executeYieldRotationWithProof` on-chain
  * `nav_interval_sec` — emit `StrategyVault.reportNAV(signedNAV)`
    using `NAV_ORACLE_PK`, mirrors the momentum/MR runtime exactly

Yield-rotation is structurally distinct from the directional classes:
no per-bar prices, no swap router, an empty `Call[]` array for Phase 2
(see `executor.py` docstring). The proof is the on-chain artifact —
the actual cross-chain rotation lands in Phase 5 with LayerZero.

Address-gated like every other Phase-2 service: dry-runs land in
`executor.pending` until `STRATEGY_VAULT_ADDRESS` lands.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import structlog
from eth_account import Account
from eth_utils.crypto import keccak

from yield_rotation_v1.executor import ExecutionRecord, TradeExecutor
from yield_rotation_v1.oracle_client import YieldOracleClient
from yield_rotation_v1.prover_client import ProofResult, ProverClient, ProverDegraded
from yield_rotation_v1.strategy import YieldRotationStrategy
from yield_rotation_v1.types import YieldTick
from yield_rotation_v1.witness import build_yield_rotation_witness

_log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    yield_interval_sec: int = 300
    nav_interval_sec: int = 300
    block_window_size: int = 50
    nonce_seed: int = 0
    declared_class_field: int = 0


@dataclass
class RuntimeStats:
    ticks_observed: int = 0
    signals_fired: int = 0
    proofs_generated: int = 0
    proof_failures: int = 0
    execs_submitted: int = 0
    nav_reports: int = 0
    last_block_window_end: int = 0
    last_error: str = ""
    last_signal: dict[str, Any] = field(default_factory=dict)


class YieldRotationRuntime:
    """Glues the YR strategy to the live yield-oracle + proof pipeline."""

    def __init__(
        self,
        *,
        strategy: YieldRotationStrategy,
        oracle: YieldOracleClient,
        prover: ProverClient,
        executor: TradeExecutor,
        config: RuntimeConfig,
        market_subscriptions: Iterable[tuple[str, int]],
        nav_oracle_pk: str = "",
        allocator_address: str = "0x" + "0" * 40,
        block_provider: BlockProvider | None = None,
    ) -> None:
        self._strategy = strategy
        self._oracle = oracle
        self._prover = prover
        self._executor = executor
        self._cfg = config
        self._allocator_address = allocator_address
        # `market_subscriptions` is the list of (oracle market_id string,
        # registry market id int) pairs the operator polls. The string
        # keys YieldStore; the int is what the circuit + allowlist tree
        # use. Operators control this mapping in their config.
        self._subs = list(market_subscriptions)
        if not self._subs:
            raise ValueError("market_subscriptions must be non-empty")
        self._nav_signer = (
            Account.from_key(_normalize_pk(nav_oracle_pk)) if nav_oracle_pk else None
        )
        self._block_provider = block_provider or _DummyBlockProvider()
        self._nonce = config.nonce_seed
        self._yield_task: asyncio.Task[None] | None = None
        self._nav_task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self.stats = RuntimeStats()
        self._records: list[ExecutionRecord] = []

    @property
    def records(self) -> list[ExecutionRecord]:
        return list(self._records)

    # ── Lifecycle ─────────────────────────────────────────────
    def start(self) -> None:
        if self._yield_task is None:
            self._stop.clear()
            self._yield_task = asyncio.create_task(
                self._yield_loop(), name="yield_rotation.ticks"
            )
            self._nav_task = asyncio.create_task(
                self._nav_loop(), name="yield_rotation.nav"
            )

    async def stop(self) -> None:
        self._stop.set()
        for t in (self._yield_task, self._nav_task):
            if t is not None:
                await t
        self._yield_task = None
        self._nav_task = None
        await self._oracle.aclose()
        await self._prover.aclose()

    # ── Yield tick ────────────────────────────────────────────
    async def _yield_loop(self) -> None:
        while not self._stop.is_set():
            await self.tick_yield()
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=self._cfg.yield_interval_sec
                )
            except TimeoutError:
                continue

    async def tick_yield(self) -> ExecutionRecord | None:
        """Poll oracle → on_yield_tick → maybe prove + execute.

        Returns the produced record or `None` when the strategy holds
        or witness/proof building fails. Used by tests + scenario
        harnesses."""
        ticks: dict[int, YieldTick] = {}
        for market_str, registry_id in self._subs:
            try:
                tick = await self._oracle.fetch_latest_tick(market_str, registry_id)
            except Exception as exc:
                _log.warning(
                    "yield_rotation.oracle.error", market=market_str, err=str(exc)
                )
                self.stats.last_error = str(exc)
                continue
            if tick is None:
                continue
            ticks[registry_id] = tick
        if not ticks:
            return None
        self.stats.ticks_observed += 1
        intent = self._strategy.on_yield_tick(ticks)
        if intent is None:
            return None
        self.stats.signals_fired += 1
        return await self._handle_signal(intent, ticks)

    async def _handle_signal(
        self,
        intent: Any,
        ticks: dict[int, YieldTick],
    ) -> ExecutionRecord | None:
        block_start, block_end = self._block_provider.window(self._cfg.block_window_size)
        del block_start  # YR circuit only uses block_window_end
        self._nonce += 1
        nonce = self._nonce

        snapshots = list(ticks.values())
        try:
            request = build_yield_rotation_witness(
                intent=intent,
                yield_snapshots=snapshots,
                allowlisted_markets=list(self._strategy.allowlisted_markets),
                declared_class_field=self._cfg.declared_class_field,
                allocator_address=self._allocator_address,
                nonce=nonce,
                block_window_end=block_end,
                signal_threshold_bps=self._strategy.signal_threshold_bps,
                bridging_cost_bps=self._strategy.bridging_cost_bps,
            )
        except ValueError as exc:
            _log.warning("yield_rotation.witness.invalid", err=str(exc))
            self.stats.last_error = str(exc)
            return None

        try:
            proof: ProofResult = await self._prover.prove(
                strategy_class=request.strategy_class, witness_inputs=request.inputs
            )
        except ProverDegraded as exc:
            _log.warning("yield_rotation.prover.degraded", err=str(exc))
            self.stats.proof_failures += 1
            self.stats.last_error = str(exc)
            return None

        self.stats.proofs_generated += 1
        record = self._executor.submit(
            self._executor.build_plan(
                proof=_proof_to_bytes(proof.proof),
                public_inputs=[int(s) for s in proof.public_signals],
                trades=[],
            ),
            m_from=intent.m_from,
            m_to=intent.m_to,
            amount_in_usd=intent.amount_in_usd,
            block_window_end=block_end,
        )
        self._records.append(record)
        self.stats.execs_submitted += 1
        self.stats.last_block_window_end = block_end
        self.stats.last_signal = {
            "m_from": intent.m_from,
            "m_to": intent.m_to,
            "amount_in_usd": intent.amount_in_usd,
            "nonce": nonce,
        }
        # Reflect the rotation in the strategy's local state so the next
        # tick keys off the new active market.
        self._strategy.set_active_market(intent.m_to)
        return record

    # ── NAV tick ──────────────────────────────────────────────
    async def _nav_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=self._cfg.nav_interval_sec
                )
            except TimeoutError:
                self.tick_nav(self._strategy.available_capital)

    def tick_nav(
        self, total_nav_usd: float, *, timestamp: int | None = None
    ) -> ExecutionRecord:
        """Sign + submit one NAV report. Mirrors momentum's runtime — the
        StrategyVault digest is `keccak256(abi.encode(vault, totalNAV,
        timestamp))` recovering to `navOracle`."""
        if self._nav_signer is None:
            raise RuntimeError("nav_oracle_pk required for tick_nav")
        ts = timestamp if timestamp is not None else int(time.time())
        total_nav_e18 = int(total_nav_usd * 10**18)
        vault_word = (
            bytes.fromhex(self._executor.vault[2:].rjust(40, "0"))
            if self._executor.vault
            else b"\x00" * 20
        )
        body = (
            b"\x00" * 12
            + vault_word
            + total_nav_e18.to_bytes(32, "big")
            + ts.to_bytes(32, "big")
        )
        digest = keccak(body)
        sig = self._nav_signer._key_obj.sign_msg_hash(digest)  # type: ignore[attr-defined]
        signature = sig.to_bytes()
        self.stats.nav_reports += 1
        return self._executor.submit_nav(
            total_nav_e18=total_nav_e18, timestamp=ts, nav_signature=signature
        )


# ── Block-window resolver ────────────────────────────────────
class BlockProvider:
    def window(self, size: int) -> tuple[int, int]:
        raise NotImplementedError


class _DummyBlockProvider(BlockProvider):
    def __init__(self, start: int = 1) -> None:
        self._n = start

    def window(self, size: int) -> tuple[int, int]:
        start = self._n
        self._n += 1
        return start, start + size


def _normalize_pk(pk: str) -> str:
    return pk if pk.startswith("0x") else "0x" + pk


def _proof_to_bytes(proof: dict[str, Any]) -> bytes:
    """Pack a snarkjs Groth16 proof into the 256-byte form the
    `Groth16Verifier` accepts (uint256[8] = a.x, a.y, b.x.imag, b.x.real,
    b.y.imag, b.y.real, c.x, c.y). Identical layout to the directional
    classes — see `momentum_v1.runtime._proof_to_bytes`."""
    pa = [int(x) for x in proof["pi_a"][:2]]
    pb_x = [int(x) for x in proof["pi_b"][0]]
    pb_y = [int(x) for x in proof["pi_b"][1]]
    pc = [int(x) for x in proof["pi_c"][:2]]
    words = [
        *pa,
        pb_x[1],
        pb_x[0],
        pb_y[1],
        pb_y[0],
        *pc,
    ]
    return b"".join(w.to_bytes(32, "big") for w in words)
