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
from helios.runtime.nav_seed import read_erc20_balance, seed_strategy_capital
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
    # Bars skipped because the on-demand anchor commit didn't mine
    # (endpoint disabled, gas-starved signer, RPC error). Distinct from
    # proof_failures: the proof was never attempted, so this is a safe
    # skip, not a degraded prover.
    commit_failures: int = 0
    # Signals dropped before the prover because the vault is too thinly
    # funded for `amount_in` to resolve to ≥ 1 wei. Kept distinct from
    # `proof_failures` so an under-funded vault is not conflated with a
    # genuinely broken prover (corrupt zkey, OOM, …).
    signals_unfundable: int = 0
    execs_submitted: int = 0
    nav_reports: int = 0
    last_block_window_end: int = 0
    # Spendable base-asset (mUSDC) cash from the on-chain seed. This is
    # the ceiling a LONG entry can fund and the number that explains an
    # `unfundable` skip (cash == 0 ⇒ nothing to spend even if NAV > 0).
    last_seeded_nav_usd: float = 0.0
    # Position-aware mark-to-market NAV: base cash + every non-base
    # holding valued at the latest oracle price. Drives
    # `nav_target_notional` sizing and the on-chain `reportNAV`. Diverges
    # from `last_seeded_nav_usd` exactly when the vault holds non-base
    # assets (i.e. after any swap has fired).
    last_position_nav_usd: float = 0.0
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
        # Symbol↔address lockstep: every symbol in the strategy's
        # universe must map to a non-empty address slot at the same
        # index. Without this guard, a Base-scoped address override
        # (e.g. `[Base mUSDC, WETH9, "", ...]`) paired with the default
        # 4-symbol strategy universe would silently route WBTC signals
        # to the WETH9 address (slot 1 holds WETH9 in the override but
        # `_asset_idx["WBTC"] == 1`), executing a USDC→WETH9 swap that
        # the on-chain vault accepts (witness addr[1] == vault.universe[1])
        # while the strategy's mental model thinks it bought WBTC.
        # Slippage doesn't catch the miswiring because actual WETH
        # output far exceeds the strategy's WBTC-priced min_out.
        for i, sym in enumerate(strategy.asset_universe):
            if not self._universe[i]:
                raise ValueError(
                    f"asset_universe symbol/address lockstep violated: strategy "
                    f"index {i} ({sym!r}) has no address in the universe override"
                )
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
        base_cash_usd = self._seed_nav_from_chain()
        # `observed` gates the NAV write: a bar where neither the base
        # cash nor any holding could be read must NOT clobber a last-good
        # NAV to 0 — the 300s reportNAV cadence would then post a false
        # zero. Genuine 0 balances (read succeeded, vault empty) DO count
        # as observed and update NAV.
        observed = base_cash_usd is not None
        nav_usd = base_cash_usd or 0.0
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
            # Position-aware NAV: every LONG entry swaps mUSDC → asset,
            # so without crediting the held asset back, NAV reads ~0 once
            # cash is spent and `nav_target_notional` sizes every entry
            # to 0 (the vault gets permanently stuck). Mark each holding
            # to the latest signed oracle price in this bundle.
            held = self._holding_value_usd(asset, bundle)
            if held is not None:
                nav_usd += held
                observed = True
            self.stats.bars_observed += 1
            intent = self._strategy.on_bar(asset, bundle.market)
            if intent is None:
                continue
            self.stats.signals_fired += 1
            record = await self._handle_signal(asset, intent, bundle)
            if record is not None:
                produced.append(record)
        # NAV is set once per bar, after every holding is priced. on_bar
        # this bar saw the prior bar's NAV (one 60s warmup after a cold
        # start, since the position book is empty until the first fetch);
        # the 300s reportNAV cadence always reads the fresh value.
        if self._executor.live and observed:
            self._strategy._set_nav(nav_usd)
            self.stats.last_position_nav_usd = nav_usd
        return produced

    def _holding_value_usd(self, asset: str, bundle: SnapshotBundle) -> float | None:
        """USD value of the vault's on-chain balance of `asset`, marked
        to the latest signed oracle price in `bundle`.

        Returns 0.0 when the read succeeded but the vault holds none of
        the asset (a real observation). Returns None when the value
        could not be observed — dry-run, unknown asset, or a failed
        balanceOf — so the caller leaves NAV at its last-good value
        instead of treating an RPC blip as a $0 position."""
        if not self._executor.live:
            return None
        idx = self._asset_idx.get(asset)
        if idx is None:
            return None
        token = self._universe[idx]
        if not token or not bundle.signed:
            return None
        dec = (self._cfg.asset_decimals or {}).get(asset, 18)
        try:
            raw = read_erc20_balance(
                w3=self._executor.w3,
                token_address=token,
                holder_address=self._executor.vault,
            )
        except Exception as exc:
            _log.warning("mean_reversion.nav.holding_read_failed", asset=asset, err=str(exc))
            return None
        if raw <= 0:
            return 0.0
        price_usd = bundle.signed[-1].price_e18 / 1e18
        return (raw / (10**dec)) * price_usd

    async def _handle_signal(
        self,
        asset: str,
        intent: TradeIntent,
        bundle: SnapshotBundle,
    ) -> ExecutionRecord | None:
        # Commit-on-demand: anchor a fresh root for this asset NOW so the
        # proof's `oracle_root` is ~0s old against StrategyVault's 180s
        # freshness gate, then re-fetch so the witness proves exactly the
        # just-committed window. The oracle now serves view=committed and
        # recorded the mirror synchronously before returning, so the
        # re-fetch is race-free. (A snapshot landing in the sub-second
        # gap since tick_bar's fetch could shift the window by one bar
        # vs. the signal; the circuit re-derives the signal from these
        # observations, so a no-longer-crossing window fails the proof —
        # a safe skip, never a bad trade.) Any commit failure is a safe
        # skip, strictly better than an on-chain UnknownOracleRoot.
        try:
            await self._oracle.request_commit(asset)
            bundle = await self._oracle.fetch_recent(asset, PRICE_OBSERVATIONS)
        except OracleEmptyError:
            return None
        except Exception as exc:
            _log.warning("mean_reversion.anchor.commit_failed", asset=asset, err=str(exc))
            self.stats.commit_failures += 1
            self.stats.last_error = str(exc)
            return None

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
                # Clamp `amount_in` to the vault's exact integer balance
                # so the swap's `safeTransferFrom` cannot revert on a
                # float-roundtrip drift from `seed_strategy_capital`.
                base_asset_balance_raw=self._strategy._base_asset_balance_wei,
            )
        except ValueError as exc:
            _log.warning("mean_reversion.witness.invalid", asset=asset, err=str(exc))
            self.stats.last_error = str(exc)
            return None

        amount_in = int(request.inputs["amount_in"])
        if amount_in < 1:
            # NAV-seed rounded the position to 0 wei (worst on the
            # low-decimal legs — WBTC 8-dec, WSOL 9-dec). The circuit's
            # Constraint 0 (`amount_in > 0`, mean_reversion_v1.circom:165)
            # would reject this, but proving it anyway burns a witness-gen
            # cycle and surfaces as an indistinguishable `prover.degraded`.
            # Skip with an honest, greppable signal pointing at the real
            # cause: the vault is under-funded.
            _log.warning(
                "mean_reversion.signal.unfundable",
                asset=asset,
                amount_in=amount_in,
                # cash == 0 while position_nav > 0 is the diagnostic
                # signature of "vault drained to assets, no base leg to
                # spend" — it can only recover by exiting a held position.
                seeded_cash_usd=self.stats.last_seeded_nav_usd,
                position_nav_usd=self.stats.last_position_nav_usd,
            )
            self.stats.signals_unfundable += 1
            self.stats.last_error = "amount_in resolved to 0 wei — strategy vault under-funded"
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
        # Diagnostic (TradeCallFailed(1) root-cause): emit the exact swap
        # params so the witness `min_amount_out` can be compared against
        # the live MockSwapRouter fill (amount_in * priceOf.num/denom).
        _log.info(
            "mean_reversion.exec.params",
            asset=asset,
            asset_in=intent.asset_in,
            asset_out=intent.asset_out,
            token_in=self._universe[self._asset_idx[intent.asset_in]],
            token_out=self._universe[self._asset_idx[intent.asset_out]],
            amount_in=request.inputs["amount_in"],
            expected_amount_out=request.inputs["expected_amount_out"],
            min_amount_out=request.inputs["min_amount_out"],
            last_price_e18=request.inputs["price_observations"][-1],
            pow10_in=request.inputs["pow10_asset_in"],
            pow10_out=request.inputs["pow10_asset_out"],
            max_slippage_bps=intent.max_slippage_bps,
            nonce=nonce,
        )
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
    def _seed_nav_from_chain(self) -> float | None:
        """Seed `available_capital` (spendable base cash) + the exact
        wei balance from `IERC20(USDC).balanceOf(vault)`, and return that
        cash in USD. NAV is *not* set here — `tick_bar` owns a
        position-aware NAV (base cash + every non-base holding marked to
        the latest oracle price). Seeding NAV to base-cash-only would
        report ~0 once the vault has swapped its base leg into assets,
        collapsing `nav_target_notional` sizing.

        Returns the cash USD when observed (0.0 is a valid observation —
        an empty base leg). Returns None when it could not be read
        (dry-run or a failed RPC) so `tick_bar` keeps the last-good NAV
        rather than posting a false zero."""
        if not self._executor.live:
            return None
        base_asset = self._universe[0] if self._universe else ""
        if not base_asset:
            return None
        try:
            cash = seed_strategy_capital(
                strategy=self._strategy,
                w3=self._executor.w3,
                base_asset_address=base_asset,
                vault_address=self._executor.vault,
                base_asset_decimals=self._cfg.asset_decimals.get("USDC", 18)
                if self._cfg.asset_decimals
                else 18,
                set_nav=False,
            )
            self.stats.last_seeded_nav_usd = cash
            return cash
        except Exception as exc:
            _log.warning("mean_reversion.nav.seed_failed", err=str(exc))
            return None

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
        `navOracle`.

        NAV is reported in the base asset's *native* units so it can be
        compared against `_manifest.maxCapacity`, which the deploy
        scripts denominate in those same native units (1e6 on Base for
        6-dec mUSDC, 1e18 on Kite for 18-dec mUSDC). Always scaling by
        1e18 here would inflate the Base value by 1e12 and trip the
        `NavExceedsCap` check (`totalNAV_ > 10 * maxCapacity`).
        """
        if self._nav_signer is None:
            raise RuntimeError("nav_oracle_pk required for tick_nav")
        ts = timestamp if timestamp is not None else int(time.time())
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
