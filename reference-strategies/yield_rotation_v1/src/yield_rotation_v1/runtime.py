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
from eth_account.messages import encode_typed_data
from helios.runtime.nav_seed import seed_strategy_capital

from yield_rotation_v1.executor import ExecutionRecord, TradeExecutor
from yield_rotation_v1.oracle_client import YieldOracleClient
from yield_rotation_v1.prover_client import ProofResult, ProverClient, ProverDegraded
from yield_rotation_v1.strategy import YieldRotationStrategy
from yield_rotation_v1.types import YieldTick
from yield_rotation_v1.witness import build_yield_rotation_witness

_log = structlog.get_logger(__name__)

# Minimal views to resolve the vault's base asset + its decimals on
# chain, so the NAV seed works on any chain (Kite mUSDC 18-dec,
# Base/Arb 6-dec) without hardcoding an address.
_VAULT_BASEASSET_ABI = [
    {
        "name": "baseAsset",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "address"}],
    }
]
_ERC20_DECIMALS_ABI = [
    {
        "name": "decimals",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "uint8"}],
    }
]


def _sign_nav_eip712(
    *,
    signer: Any,
    chain_id: int,
    vault_address: str,
    total_nav: int,
    timestamp: int,
) -> bytes:
    """65-byte EIP-712 signature over `NAVUpdate(totalNAV, timestamp)`
    bound to the StrategyVault domain. Bit-exact match for
    `_hashTypedDataV4(structHash)` inside `StrategyVault.reportNAV`."""
    if not vault_address:
        raise ValueError("vault_address required for NAV signing")
    domain = {
        "name": "HeliosStrategyVault",
        "version": "1",
        "chainId": chain_id,
        "verifyingContract": vault_address,
    }
    types = {
        "NAVUpdate": [
            {"name": "totalNAV", "type": "uint256"},
            {"name": "timestamp", "type": "uint64"},
        ]
    }
    message = {"totalNAV": total_nav, "timestamp": timestamp}
    encoded = encode_typed_data(domain_data=domain, message_types=types, message_data=message)
    return bytes(signer.sign_message(encoded).signature)


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    yield_interval_sec: int = 300
    nav_interval_sec: int = 300
    block_window_size: int = 50
    nonce_seed: int = 0
    declared_class_field: int = 0
    # Base-asset decimals by symbol (e.g. {"USDC": 6} on Arb). None →
    # legacy 18-dec NAV encoding (preserves Kite behavior bit-for-bit).
    asset_decimals: dict[str, int] | None = None


@dataclass
class RuntimeStats:
    ticks_observed: int = 0
    signals_fired: int = 0
    proofs_generated: int = 0
    proof_failures: int = 0
    # Signals dropped before the prover because the vault is too thinly
    # funded for `amount_rotating` to resolve to ≥ 1 wei. Kept distinct
    # from `proof_failures` so an under-funded vault is not conflated
    # with a genuinely broken prover (corrupt zkey, OOM, …).
    signals_unfundable: int = 0
    execs_submitted: int = 0
    nav_reports: int = 0
    # NAV ticks skipped because the on-chain base-asset balance read
    # failed — the report is deferred rather than submitting a stale /
    # zero value below the vault's cash floor (which trips
    # StrategyVault's NAV-divergence gate).
    nav_seed_failures: int = 0
    last_block_window_end: int = 0
    # Spendable base-asset (mUSDC) cash from the on-chain seed — the
    # NAV yr reports. Without seeding this yr submits strategy.nav≈0.
    last_seeded_nav_usd: float = 0.0
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
        strategy_vault_address: str = "0x" + "0" * 40,
        block_provider: BlockProvider | None = None,
    ) -> None:
        self._strategy = strategy
        self._oracle = oracle
        self._prover = prover
        self._executor = executor
        self._cfg = config
        self._allocator_address = allocator_address
        self._strategy_vault_address = strategy_vault_address
        # `market_subscriptions` is the list of (oracle market_id string,
        # registry market id int) pairs the operator polls. The string
        # keys YieldStore; the int is what the circuit + allowlist tree
        # use. Operators control this mapping in their config.
        self._subs = list(market_subscriptions)
        if not self._subs:
            raise ValueError("market_subscriptions must be non-empty")
        self._nav_signer = Account.from_key(_normalize_pk(nav_oracle_pk)) if nav_oracle_pk else None
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
            self._yield_task = asyncio.create_task(self._yield_loop(), name="yield_rotation.ticks")
            self._nav_task = asyncio.create_task(self._nav_loop(), name="yield_rotation.nav")

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
                await asyncio.wait_for(self._stop.wait(), timeout=self._cfg.yield_interval_sec)
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
                _log.warning("yield_rotation.oracle.error", market=market_str, err=str(exc))
                self.stats.last_error = str(exc)
                continue
            if tick is None:
                continue
            ticks[registry_id] = tick
        if not ticks:
            return None
        self.stats.ticks_observed += 1
        try:
            intent = self._strategy.on_yield_tick(ticks)
        except ValueError as exc:
            # Unlike momentum/mean_reversion (float `amount_in` that
            # floors to 0 in the witness builder), `RotationIntent`
            # int-coerces `amount_in_usd` and rejects `<= 0` at
            # construction (helios/types.py). So an under-funded vault
            # surfaces *here*, as a sub-$1 rotation that can't even build
            # an intent. Without this catch the ValueError propagates out
            # of `_tick_loop` and kills the tick loop entirely. Treat the
            # positivity failure as the same "vault under-funded" signal;
            # re-raise anything else (e.g. an m_from==m_to logic bug must
            # not be silently swallowed).
            if "positive" not in str(exc):
                raise
            _log.warning("yield_rotation.signal.unfundable", err=str(exc))
            self.stats.signals_fired += 1
            self.stats.signals_unfundable += 1
            self.stats.last_error = "rotation notional resolved to 0 — strategy vault under-funded"
            return None
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
        self._nonce += 1
        nonce = self._nonce

        snapshots = list(ticks.values())
        try:
            request = build_yield_rotation_witness(
                intent=intent,
                yield_snapshots=snapshots,
                allowlisted_markets=list(self._strategy.allowlisted_markets),
                declared_class_field=self._cfg.declared_class_field,
                strategy_vault=self._strategy_vault_address,
                allocator_address=self._allocator_address,
                nonce=nonce,
                block_window_end=block_end,
                block_window_start=block_start,
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
                await asyncio.wait_for(self._stop.wait(), timeout=self._cfg.nav_interval_sec)
            except TimeoutError:
                if self._executor.live:
                    seeded = self._seed_nav_from_chain()
                    if seeded is None:
                        # On-chain read failed: defer this report rather
                        # than submit a stale/zero NAV below the vault's
                        # cash floor (which trips StrategyVault's
                        # NAV-divergence gate). Next tick retries.
                        continue
                self.tick_nav(self._strategy.nav)

    def _seed_nav_from_chain(self) -> float | None:
        """Seed `strategy.nav` from the vault's on-chain base-asset
        balance so `reportNAV` is at least the cash floor.

        yr never marked NAV to chain: it submitted `strategy.nav` (≈0)
        while the vault held idle mUSDC, so every report landed >5%
        below `baseAsset.balanceOf(vault)`. StrategyVault's
        `_checkNavDivergence` then accumulated breaches every tick — and
        its uint8 counter overflowed at 255 (Panic 0x11), permanently
        bricking `reportNAV` for the vault. Reporting ≥ the cash floor
        makes `_checkNavDivergence` take a reset branch instead.

        Returns the seeded USD, or None if the on-chain read failed (the
        caller defers the NAV report that tick rather than post a value
        below the floor)."""
        if not self._executor.live:
            return None
        try:
            w3 = self._executor.w3
            # `self._executor.live` (guarded above) lazily builds the
            # Web3, so `w3` is non-None here — narrow it for the typechecker
            # (same `assert ... is not None` invariant idiom as executor.py).
            assert w3 is not None
            vault = w3.to_checksum_address(self._executor.vault)
            base_asset = (
                w3.eth.contract(address=vault, abi=_VAULT_BASEASSET_ABI)
                .functions.baseAsset()
                .call()
            )
            decimals = (
                w3.eth.contract(address=w3.to_checksum_address(base_asset), abi=_ERC20_DECIMALS_ABI)
                .functions.decimals()
                .call()
            )
            usd = seed_strategy_capital(
                strategy=self._strategy,
                w3=w3,
                base_asset_address=base_asset,
                vault_address=vault,
                base_asset_decimals=decimals,
                set_nav=True,
            )
            self.stats.last_seeded_nav_usd = usd
            return usd
        except Exception as exc:
            _log.warning("yield_rotation.nav.seed_failed", err=str(exc))
            self.stats.nav_seed_failures += 1
            self.stats.last_error = str(exc)
            return None

    def tick_nav(self, total_nav_usd: float, *, timestamp: int | None = None) -> ExecutionRecord:
        """Sign + submit one NAV report. Mirrors momentum's runtime — the
        StrategyVault verifies an EIP-712 typed-data signature with
        domain `(name="HeliosStrategyVault", version="1", chainId,
        verifyingContract=vault)` over `NAVUpdate(uint256 totalNAV,
        uint64 timestamp)`, recovering to `navOracle`."""
        if self._nav_signer is None:
            raise RuntimeError("nav_oracle_pk required for tick_nav")
        ts = timestamp if timestamp is not None else int(time.time())
        # NAV is reported in the base asset's *native* units so it can be
        # compared against `_manifest.maxCapacity`, which the deploy
        # scripts denominate in those same units (1e18 on Kite for 18-dec
        # mUSDC, 1e6 on Arb for 6-dec mUSDC). Always scaling by 1e18 here
        # would inflate the Arb value by 1e12 and trip `NavExceedsCap`
        # (`totalNAV_ > 10 * maxCapacity`).
        base_decimals = self._cfg.asset_decimals.get("USDC", 18) if self._cfg.asset_decimals else 18
        total_nav_native = int(total_nav_usd * 10**base_decimals)
        signature = _sign_nav_eip712(
            signer=self._nav_signer,
            chain_id=self._executor.chain_id,
            vault_address=self._executor.vault,
            total_nav=total_nav_native,
            timestamp=ts,
        )
        self.stats.nav_reports += 1
        return self._executor.submit_nav(
            total_nav_e18=total_nav_native, timestamp=ts, nav_signature=signature
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


class Web3BlockProvider(BlockProvider):
    """Reads `eth_blockNumber` from the operator's RPC. Mirrors
    momentum/mean_reversion's `Web3BlockProvider`; required for the
    witness's `[block_window_start, block_window_end]` to bracket
    the on-chain `block.number` at `executeWithProof` time."""

    _BACK_BUFFER = 5

    def __init__(self, w3: Any) -> None:
        self._w3 = w3

    def window(self, size: int) -> tuple[int, int]:
        head = int(self._w3.eth.block_number)
        start = max(0, head - self._BACK_BUFFER)
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
