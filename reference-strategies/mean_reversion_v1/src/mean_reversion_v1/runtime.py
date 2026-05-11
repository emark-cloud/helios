"""Runtime that drives the reference mean_reversion_v1 strategy.

Two async cadences:
  * `bar_interval_sec` — pull oracle snapshots, run `on_bar` per
    asset, prove + execute on signal.
  * `nav_interval_sec` — emit `StrategyVault.reportNAV(signedNAV)`
    using the local `NAV_ORACLE_PK`.

Mean-reversion's signal logic surfaces two extra flags after `on_bar`
fires (`is_signal_flip` and `is_stop_loss`); the runtime forwards both
to the witness builder so the circuit's exit-reason gate is satisfied.
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
from helios.types import TradeIntent

from mean_reversion_v1.executor import ExecutionRecord, TradeExecutor
from mean_reversion_v1.oracle_client import OracleClient, OracleEmptyError, SnapshotBundle
from mean_reversion_v1.prover_client import ProofResult, ProverClient, ProverDegraded
from mean_reversion_v1.strategy import MeanReversionStrategy
from mean_reversion_v1.witness import PRICE_OBSERVATIONS, build_mean_reversion_witness

_log = structlog.get_logger(__name__)


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
    bar_interval_sec: int = 60
    nav_interval_sec: int = 300
    block_window_size: int = 50  # circuit ceiling 100; leaves headroom
    nonce_seed: int = 0
    declared_class_field: int = 0  # filled at startup from manifest
    # Phase-6 multi-asset: per-symbol raw decimals so the witness builder
    # encodes `amount_in` in `tokenIn`'s native decimals. None or empty
    # keeps the Phase-1 USD*10^18 legacy mode (see witness._resolve_amount_in).
    asset_decimals: dict[str, int] | None = None


@dataclass
class RuntimeStats:
    bars_observed: int = 0
    signals_fired: int = 0
    proofs_generated: int = 0
    proof_failures: int = 0
    execs_submitted: int = 0
    nav_reports: int = 0
    last_block_window_end: int = 0
    last_seeded_nav_usd: float = 0.0
    last_error: str = ""
    last_signal: dict[str, Any] = field(default_factory=dict)


class MeanReversionRuntime:
    """Glues the strategy class to the live data + proof pipeline."""

    def __init__(
        self,
        *,
        strategy: MeanReversionStrategy,
        oracle: OracleClient,
        prover: ProverClient,
        executor: TradeExecutor,
        config: RuntimeConfig,
        nav_oracle_pk: str = "",
        allocator_address: str = "0x" + "0" * 40,
        asset_universe_addresses: Iterable[str] | None = None,
        block_provider: BlockProvider | None = None,
    ) -> None:
        self._strategy = strategy
        self._oracle = oracle
        self._prover = prover
        self._executor = executor
        self._cfg = config
        self._allocator_address = allocator_address
        if asset_universe_addresses is not None:
            self._universe = list(asset_universe_addresses)
        else:
            self._universe = list(strategy.asset_universe) + [""] * (
                8 - len(strategy.asset_universe)
            )
        if len(self._universe) != 8:
            raise ValueError("asset_universe_addresses must produce exactly 8 entries")
        self._asset_idx = {a: i for i, a in enumerate(strategy.asset_universe)}
        self._nav_signer = Account.from_key(_normalize_pk(nav_oracle_pk)) if nav_oracle_pk else None
        self._block_provider = block_provider or _DummyBlockProvider()
        self._nonce = config.nonce_seed
        self._bar_task: asyncio.Task[None] | None = None
        self._nav_task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self.stats = RuntimeStats()
        self._records: list[ExecutionRecord] = []

    @property
    def records(self) -> list[ExecutionRecord]:
        return list(self._records)

    # ── Lifecycle ─────────────────────────────────────────────
    def start(self) -> None:
        if self._bar_task is None:
            self._stop.clear()
            self._bar_task = asyncio.create_task(self._bar_loop(), name="mean_reversion.bars")
            self._nav_task = asyncio.create_task(self._nav_loop(), name="mean_reversion.nav")

    async def stop(self) -> None:
        self._stop.set()
        for t in (self._bar_task, self._nav_task):
            if t is not None:
                await t
        self._bar_task = None
        self._nav_task = None
        await self._oracle.aclose()
        await self._prover.aclose()

    # ── Bar tick ──────────────────────────────────────────────
    async def _bar_loop(self) -> None:
        while not self._stop.is_set():
            await self.tick_bar()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._cfg.bar_interval_sec)
            except TimeoutError:
                continue

    async def tick_bar(self) -> list[ExecutionRecord]:
        self._seed_nav_from_chain()
        produced: list[ExecutionRecord] = []
        for asset in self._strategy.asset_universe:
            if asset == "USDC":
                continue
            try:
                bundle = await self._oracle.fetch_recent(asset, PRICE_OBSERVATIONS)
            except OracleEmptyError:
                continue
            except Exception as exc:
                _log.warning("mean_reversion.oracle.error", asset=asset, err=str(exc))
                self.stats.last_error = str(exc)
                continue
            self.stats.bars_observed += 1
            intent = self._strategy.on_bar(asset, bundle.market)
            if intent is None:
                continue
            self.stats.signals_fired += 1
            record = await self._handle_signal(asset, intent, bundle)
            if record is not None:
                produced.append(record)
        return produced

    async def _handle_signal(
        self,
        asset: str,
        intent: TradeIntent,
        bundle: SnapshotBundle,
    ) -> ExecutionRecord | None:
        block_start, block_end = self._block_provider.window(self._cfg.block_window_size)
        prices_e18 = [s.price_e18 for s in bundle.signed]
        self._nonce += 1
        nonce = self._nonce

        try:
            request = build_mean_reversion_witness(
                intent=intent,
                asset_to_universe_idx=self._asset_idx,
                asset_universe_addresses=self._universe,
                price_observations_e18=prices_e18,
                declared_class_field=self._cfg.declared_class_field,
                strategy_vault_address=self._executor.vault or "0x" + "0" * 40,
                allocator_address=self._allocator_address,
                nonce=nonce,
                block_window_start=block_start,
                block_window_end=block_end,
                max_position_size_e18=self._strategy.max_position_size_usd * 10**18,
                max_slippage_bps=intent.max_slippage_bps,
                n_sigma_x100=self._strategy.n_sigma_x100,
                stop_loss_price_e18=int(self._strategy.stop_loss_price * 10**18),
                is_signal_flip=intent.is_signal_flip,
                is_stop_loss=intent.is_stop_loss,
                # Phase-6 multi-asset: switches the witness builder to
                # raw-tokenIn encoding so `amount_in` matches the on-chain
                # swap amount across mixed-decimal universes.
                asset_decimals=self._cfg.asset_decimals,
            )
        except ValueError as exc:
            _log.warning("mean_reversion.witness.invalid", asset=asset, err=str(exc))
            self.stats.last_error = str(exc)
            return None

        try:
            proof: ProofResult = await self._prover.prove(
                strategy_class=request.strategy_class, witness_inputs=request.inputs
            )
        except ProverDegraded as exc:
            _log.warning("mean_reversion.prover.degraded", asset=asset, err=str(exc))
            self.stats.proof_failures += 1
            self.stats.last_error = str(exc)
            return None

        self.stats.proofs_generated += 1
        record = self._executor.submit(
            self._executor.build_plan(
                proof=_proof_to_bytes(proof.proof),
                public_inputs=[int(s) for s in proof.public_signals],
                token_in=self._universe[self._asset_idx[intent.asset_in]],
                token_out=self._universe[self._asset_idx[intent.asset_out]],
                amount_in=int(request.inputs["amount_in"]),
                min_amount_out=int(request.inputs["min_amount_out"]),
                deadline_unix=int(time.time()) + 300,
            ),
            asset=asset,
            direction=int(intent.direction),
            block_window_end=block_end,
        )
        self._records.append(record)
        self.stats.execs_submitted += 1
        self.stats.last_block_window_end = block_end
        self.stats.last_signal = {
            "asset": asset,
            "direction": int(intent.direction),
            "amount_in": int(request.inputs["amount_in"]),
            "is_signal_flip": int(intent.is_signal_flip),
            "is_stop_loss": int(intent.is_stop_loss),
            "nonce": nonce,
        }
        return record

    # ── NAV seed from on-chain balance ────────────────────────
    def _seed_nav_from_chain(self) -> None:
        """Read `IERC20(USDC).balanceOf(vault)` and set the strategy's
        `available_capital` + `nav` to that value. Without this seed
        `_size()` returns 0 (NAV = 0), which the directional circuit
        rejects via Constraint 0 (`amount_in > 0`). Silently no-ops in
        dry-run mode (no live web3) so unit tests don't need a chain."""
        if not self._executor.live:
            return
        base_asset = self._universe[0] if self._universe else ""
        if not base_asset:
            return
        try:
            seeded = seed_strategy_capital(
                strategy=self._strategy,
                w3=self._executor.w3,
                base_asset_address=base_asset,
                vault_address=self._executor.vault,
                base_asset_decimals=self._cfg.asset_decimals.get("USDC", 18)
                if self._cfg.asset_decimals
                else 18,
            )
            self.stats.last_seeded_nav_usd = seeded
        except Exception as exc:
            _log.warning("mean_reversion.nav.seed_failed", err=str(exc))

    # ── NAV tick ──────────────────────────────────────────────
    async def _nav_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._cfg.nav_interval_sec)
            except TimeoutError:
                self.tick_nav(self._strategy.nav)

    def tick_nav(self, total_nav_usd: float, *, timestamp: int | None = None) -> ExecutionRecord:
        """Sign + submit one NAV report. StrategyVault verifies an
        EIP-712 typed-data signature with domain `(name="HeliosStrategy
        Vault", version="1", chainId, verifyingContract=vault)` over
        `NAVUpdate(uint256 totalNAV, uint64 timestamp)`, recovering to
        `navOracle`."""
        if self._nav_signer is None:
            raise RuntimeError("nav_oracle_pk required for tick_nav")
        ts = timestamp if timestamp is not None else int(time.time())
        total_nav_e18 = int(total_nav_usd * 10**18)
        signature = _sign_nav_eip712(
            signer=self._nav_signer,
            chain_id=self._executor.chain_id,
            vault_address=self._executor.vault,
            total_nav=total_nav_e18,
            timestamp=ts,
        )
        self.stats.nav_reports += 1
        return self._executor.submit_nav(
            total_nav_e18=total_nav_e18, timestamp=ts, nav_signature=signature
        )


# ── Block-window resolver ────────────────────────────────────
class BlockProvider:
    """Returns (start, end) block numbers for the current trade window."""

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
    """Reads `eth_blockNumber` from the operator's RPC and emits a
    window centered on the current head. The witness's
    `[block_window_start, block_window_end]` must bracket the block
    `executeWithProof` lands in (`StrategyVault.sol:481-482`); a 5-block
    buffer back covers RPC-vs-bundler skew without expanding the
    proof's blast radius."""

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
    Solidity verifier accepts: 8 × uint256.
    """
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
