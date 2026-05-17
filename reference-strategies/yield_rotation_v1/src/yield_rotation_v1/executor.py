"""Trade-execution boundary for yield_rotation_v1.

Targets `StrategyVault.executeYieldRotationWithProof(proof, publicInputs,
trades)`. Phase 2 = Kite-local-only — there are no real lending market
contracts on Kite testnet, so the `trades` array is **empty**. The
proof itself is the on-chain artifact; the actual rotation lands in
Phase 5 with cross-chain bridging via LayerZero.

When a future StrategyVault patch wires a bridging mock, this executor
gains a `build_bridging_calldata(...)` helper analogous to
`build_swap_calldata` on the directional executors. Phase 2 keeps the
surface as small as possible.

Address-gated: when `STRATEGY_VAULT_ADDRESS` is unset (CI / local dry
run) the executor records `pending` calls instead of submitting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog
from eth_abi.abi import encode as abi_encode
from eth_account import Account
from eth_utils.crypto import keccak
from helios.runtime import build_resilient_web3
from helios_contracts_abi.abis import IStrategyVault_ABI
from web3 import Web3
from web3.types import TxReceipt

from yield_rotation_v1.aave_v3 import (
    build_aave_supply_calldata,
    build_aave_withdraw_calldata,
)

_log = structlog.get_logger(__name__)

_RECEIPT_TIMEOUT_SEC = 120


@dataclass(frozen=True, slots=True)
class TradeCall:
    target: str
    value: int
    data: bytes


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    proof: bytes
    public_inputs: list[int]
    trades: list[TradeCall]


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
    plan: ExecutionPlan
    submitted: bool = False
    tx_hash: str = ""
    error: str = ""
    extras: dict[str, Any] = field(default_factory=dict)


class TradeExecutor:
    """Phase-2 Kite-only behavior is preserved by the empty default for
    `lending_pool_address`. Phase-5 Arbitrum-Sepolia callers pass the
    Aave V3 Pool address (or the MockYieldVault address) and the
    executor packs an Aave-shape supply/withdraw call into the
    `trades` array instead of leaving it empty.

    `venue_kind` is metadata only on this side — Aave V3 calldata is
    the same regardless of whether the target address is the real
    Pool or the mock vault. The deploy JSON keeps both addresses; the
    SDK's chain-config resolver picks one based on `VenueMode`."""

    def __init__(
        self,
        rpc_url: str,
        operator_pk: str,
        strategy_vault_address: str,
        chain_id: int,
        *,
        lending_pool_address: str = "",
        venue_kind: str = "passive",
    ) -> None:
        if venue_kind not in {"passive", "aave_v3"}:
            raise ValueError(f"unknown venue_kind: {venue_kind}")
        self._rpc_url = rpc_url
        self._operator_pk = operator_pk
        self._vault = strategy_vault_address
        self._chain_id = chain_id
        self._lending_pool = lending_pool_address
        self._venue_kind = venue_kind
        self._live = bool(rpc_url and operator_pk and strategy_vault_address)
        self.pending: list[ExecutionRecord] = []

        self._w3: Web3 | None = None
        self._account: Any = None
        self._vault_contract: Any = None

    @property
    def live(self) -> bool:
        return self._live

    @property
    def vault(self) -> str:
        return self._vault

    @property
    def chain_id(self) -> int:
        return self._chain_id

    @property
    def w3(self) -> Web3 | None:
        """Lazily-dialed web3 handle (None in dry-run). Lets the runtime
        read on-chain state (the NAV-seed `IERC20.balanceOf(vault)`)
        without each caller re-dialling — mirrors the momentum/MR
        executors."""
        if self._w3 is None and self._live:
            self._ensure_live()
        return self._w3

    @property
    def lending_pool(self) -> str:
        return self._lending_pool

    @property
    def venue_kind(self) -> str:
        return self._venue_kind

    # ── Plan builder ─────────────────────────────────────────
    def build_plan(
        self,
        *,
        proof: bytes,
        public_inputs: list[int],
        trades: list[TradeCall] | None = None,
    ) -> ExecutionPlan:
        return ExecutionPlan(
            proof=proof,
            public_inputs=list(public_inputs),
            trades=list(trades) if trades else [],
        )

    # ── Aave V3 calldata builders (Phase-5 Arbitrum-Sepolia) ──
    def build_aave_rotation_calls(
        self,
        *,
        from_asset: str,
        to_asset: str,
        amount: int,
        on_behalf_of: str,
    ) -> list[TradeCall]:
        """Pack a withdraw-then-supply rotation against the configured
        Aave V3 Pool. The vault is both the recipient of the withdraw
        and the owner of the new supply, so `on_behalf_of` and the
        withdraw `to` collapse to the StrategyVault address.

        Returns an empty list when `lending_pool_address` is unset,
        which matches Phase-2 Kite behavior (the runtime drops the
        local trades array and only emits the proof). A non-empty
        result requires `venue_kind == "aave_v3"` so a passive vault
        can't accidentally emit Aave-shape calldata."""
        if not self._lending_pool:
            return []
        if self._venue_kind != "aave_v3":
            raise RuntimeError("build_aave_rotation_calls requires venue_kind=aave_v3")
        withdraw_data = build_aave_withdraw_calldata(
            asset=from_asset,
            amount=amount,
            to=on_behalf_of,
        )
        supply_data = build_aave_supply_calldata(
            asset=to_asset,
            amount=amount,
            on_behalf_of=on_behalf_of,
        )
        return [
            TradeCall(target=self._lending_pool, value=0, data=withdraw_data),
            TradeCall(target=self._lending_pool, value=0, data=supply_data),
        ]

    # ── Submission ────────────────────────────────────────────
    def submit(self, plan: ExecutionPlan, **extras: Any) -> ExecutionRecord:
        record = ExecutionRecord(plan=plan, extras=dict(extras))
        if not self._live:
            self.pending.append(record)
            _log.info(
                "yield_rotation.exec.dry_run",
                vault=self._vault,
                trades=len(plan.trades),
                public_inputs_len=len(plan.public_inputs),
                proof_bytes=len(plan.proof),
            )
            return record
        try:
            tx_hash, block_number = self._submit_execute_yr(plan)
            record = ExecutionRecord(
                plan=plan,
                submitted=True,
                tx_hash=tx_hash,
                extras={**dict(extras), "block": block_number},
            )
        except Exception as exc:
            record = ExecutionRecord(
                plan=plan, submitted=False, error=str(exc), extras=dict(extras)
            )
            _log.error("yield_rotation.exec.submit_failed", vault=self._vault, err=str(exc))
        self.pending.append(record)
        return record

    # ── NAV reporting ────────────────────────────────────────
    def submit_nav(
        self,
        *,
        total_nav_e18: int,
        timestamp: int,
        nav_signature: bytes,
    ) -> ExecutionRecord:
        plan = ExecutionPlan(proof=b"", public_inputs=[], trades=[])
        record = ExecutionRecord(
            plan=plan,
            extras={
                "kind": "reportNAV",
                "total_nav_e18": total_nav_e18,
                "timestamp": timestamp,
                "signature_hex": nav_signature.hex(),
            },
        )
        if not self._live:
            self.pending.append(record)
            return record
        try:
            tx_hash, block_number = self._submit_report_nav(
                total_nav_e18=total_nav_e18, timestamp=timestamp, signature=nav_signature
            )
            record = ExecutionRecord(
                plan=plan,
                submitted=True,
                tx_hash=tx_hash,
                extras={**record.extras, "block": block_number},
            )
        except Exception as exc:
            record = ExecutionRecord(
                plan=plan, submitted=False, error=str(exc), extras=record.extras
            )
            _log.error("yield_rotation.nav.submit_failed", vault=self._vault, err=str(exc))
        self.pending.append(record)
        return record

    # ── Live submission internals ─────────────────────────────
    def _ensure_live(self) -> None:
        if self._w3 is not None:
            return
        self._w3 = build_resilient_web3(self._rpc_url)
        self._account = Account.from_key(self._operator_pk)
        self._vault_contract = self._w3.eth.contract(
            address=Web3.to_checksum_address(self._vault),
            abi=IStrategyVault_ABI,
        )

    def _send(self, fn: Any) -> tuple[str, int]:
        self._ensure_live()
        assert self._w3 is not None
        assert self._account is not None
        tx = fn.build_transaction(
            {
                "from": self._account.address,
                "nonce": self._w3.eth.get_transaction_count(self._account.address, "pending"),
                "chainId": self._chain_id,
                # 2× headroom over eth.gas_price so the tx survives a
                # base-fee bump between estimate and inclusion. Arb-Sepolia's
                # base fee drifts ~2% per block, which is enough to reject
                # a flat-price tx with `max fee per gas less than block base
                # fee` and stall the NAV loop.
                "gasPrice": self._w3.eth.gas_price * 2,
            }
        )
        signed = self._account.sign_transaction(tx)
        tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt: TxReceipt = self._w3.eth.wait_for_transaction_receipt(
            tx_hash, timeout=_RECEIPT_TIMEOUT_SEC
        )
        if receipt["status"] != 1:
            raise RuntimeError(f"tx reverted: {tx_hash.hex()}")
        return tx_hash.hex(), int(receipt["blockNumber"])

    def _submit_execute_yr(self, plan: ExecutionPlan) -> tuple[str, int]:
        self._ensure_live()
        assert self._vault_contract is not None
        trades = [(Web3.to_checksum_address(t.target), int(t.value), t.data) for t in plan.trades]
        fn = self._vault_contract.functions.executeYieldRotationWithProof(
            plan.proof, [int(p) for p in plan.public_inputs], trades
        )
        return self._send(fn)

    def _submit_report_nav(
        self, *, total_nav_e18: int, timestamp: int, signature: bytes
    ) -> tuple[str, int]:
        self._ensure_live()
        assert self._vault_contract is not None
        signed_nav = abi_encode(
            ["uint256", "uint64", "bytes"], [total_nav_e18, timestamp, signature]
        )
        fn = self._vault_contract.functions.reportNAV(signed_nav)
        return self._send(fn)


# Module-level keccak shim — kept for parity with the directional
# executors so future trade-payload helpers can reuse it.
_keccak = keccak
