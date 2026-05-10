"""Trade-execution boundary for the mean_reversion_v1 reference strategy.

Two responsibilities:

  1. Encode `MockSwapRouter.exactInputSingle` calldata for the chosen
     (asset_in, asset_out, amount_in, min_amount_out) tuple. The mock
     mirrors Algebra Integral's `exactInputSingle` ABI byte-for-byte
     so a Phase-5 swap to the real router is a deploy-address change.
  2. Encode + submit `StrategyVault.executeWithProof(proof,
     publicInputs, trades)`. MR uses the same vault entry path as
     momentum (the 14-PI directional-trade path).

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
from helios_contracts_abi.abis import IStrategyVault_ABI
from web3 import Web3
from web3.types import TxReceipt

_log = structlog.get_logger(__name__)

_RECEIPT_TIMEOUT_SEC = 30


# `function exactInputSingle((address,address,address,uint256,uint256,uint256,uint160))`
# 4-byte selector for the mock + real Algebra V3.
_EXACT_INPUT_SINGLE_SELECTOR = keccak(
    b"exactInputSingle((address,address,address,uint256,uint256,uint256,uint160))"
)[:4]


@dataclass(frozen=True, slots=True)
class TradeCall:
    """Mirrors `IStrategyVault.Call`."""

    target: str
    value: int
    data: bytes


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    """A complete `executeWithProof` payload."""

    proof: bytes
    public_inputs: list[int]
    trades: list[TradeCall]


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
    """One pending or submitted execution."""

    plan: ExecutionPlan
    submitted: bool = False
    tx_hash: str = ""
    error: str = ""
    extras: dict[str, Any] = field(default_factory=dict)


class TradeExecutor:
    def __init__(
        self,
        rpc_url: str,
        operator_pk: str,
        strategy_vault_address: str,
        mock_router_address: str,
        chain_id: int,
        deadline_buffer_sec: int = 120,
    ) -> None:
        self._rpc_url = rpc_url
        self._operator_pk = operator_pk
        self._vault = strategy_vault_address
        self._router = mock_router_address
        self._chain_id = chain_id
        self._deadline_buffer = deadline_buffer_sec
        self._live = bool(rpc_url and operator_pk and strategy_vault_address)
        self.pending: list[ExecutionRecord] = []

        # Lazy live handles — dry-run paths don't dial out.
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
    def router(self) -> str:
        return self._router

    @property
    def chain_id(self) -> int:
        return self._chain_id

    @property
    def w3(self) -> Web3 | None:
        """Lazily-dialed web3 handle. None in dry-run mode (no rpc/pk).
        Lets the runtime read on-chain state (e.g. NAV-seed
        `IERC20.balanceOf(vault)`) without each caller re-dialling."""
        if self._w3 is None and self._live:
            self._ensure_live()
        return self._w3

    # ── Calldata builders ─────────────────────────────────────
    def build_swap_calldata(
        self,
        *,
        token_in: str,
        token_out: str,
        recipient: str,
        amount_in: int,
        amount_out_minimum: int,
        deadline_unix: int,
    ) -> bytes:
        words = [
            _addr_word(token_in),
            _addr_word(token_out),
            _addr_word(recipient),
            deadline_unix.to_bytes(32, "big"),
            amount_in.to_bytes(32, "big"),
            amount_out_minimum.to_bytes(32, "big"),
            (0).to_bytes(32, "big"),  # limitSqrtPrice unused in mock
        ]
        return _EXACT_INPUT_SINGLE_SELECTOR + b"".join(words)

    def build_plan(
        self,
        *,
        proof: bytes,
        public_inputs: list[int],
        token_in: str,
        token_out: str,
        amount_in: int,
        min_amount_out: int,
        deadline_unix: int,
    ) -> ExecutionPlan:
        if not self._router:
            raise ValueError("router address required for build_plan")
        swap_data = self.build_swap_calldata(
            token_in=token_in,
            token_out=token_out,
            recipient=self._vault or "0x" + "0" * 40,
            amount_in=amount_in,
            amount_out_minimum=min_amount_out,
            deadline_unix=deadline_unix,
        )
        return ExecutionPlan(
            proof=proof,
            public_inputs=list(public_inputs),
            trades=[TradeCall(target=self._router, value=0, data=swap_data)],
        )

    # ── Submission ────────────────────────────────────────────
    def submit(self, plan: ExecutionPlan, **extras: Any) -> ExecutionRecord:
        record = ExecutionRecord(plan=plan, extras=dict(extras))
        if not self._live:
            self.pending.append(record)
            _log.info(
                "mean_reversion.exec.dry_run",
                vault=self._vault,
                trades=len(plan.trades),
                public_inputs_len=len(plan.public_inputs),
                proof_bytes=len(plan.proof),
            )
            return record
        try:
            tx_hash, block_number = self._submit_execute_with_proof(plan)
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
            _log.error("mean_reversion.exec.submit_failed", vault=self._vault, err=str(exc))
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
        """Submit `StrategyVault.reportNAV(signedNAV)`."""
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
            _log.error("mean_reversion.nav.submit_failed", vault=self._vault, err=str(exc))
        self.pending.append(record)
        return record

    # ── Live submission internals ─────────────────────────────
    def _ensure_live(self) -> None:
        if self._w3 is not None:
            return
        self._w3 = Web3(Web3.HTTPProvider(self._rpc_url))
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
                "gasPrice": self._w3.eth.gas_price,
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

    def _submit_execute_with_proof(self, plan: ExecutionPlan) -> tuple[str, int]:
        self._ensure_live()
        assert self._vault_contract is not None
        trades = [(Web3.to_checksum_address(t.target), int(t.value), t.data) for t in plan.trades]
        fn = self._vault_contract.functions.executeWithProof(
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


def _addr_word(addr: str) -> bytes:
    if addr.startswith("0x") or addr.startswith("0X"):
        raw = bytes.fromhex(addr[2:].rjust(40, "0"))
    else:
        raw = keccak(addr.encode("utf-8"))[-20:]
    return b"\x00" * 12 + raw
