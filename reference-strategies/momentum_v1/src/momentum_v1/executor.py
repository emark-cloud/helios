"""Trade-execution boundary.

Two responsibilities:

  1. Encode `MockSwapRouter.exactInputSingle` calldata for the chosen
     (asset_in, asset_out, amount_in, min_amount_out) tuple. The mock
     mirrors Algebra Integral's `exactInputSingle` ABI byte-for-byte
     so a Phase-2 swap to the real router is a deploy-address change.
  2. Encode + submit `StrategyVault.executeWithProof(proof,
     publicInputs, trades)`.

Address-gated: when `STRATEGY_VAULT_ADDRESS` is unset (Phase 1 pre-WS3
e2e), the executor records `pending` calls instead of submitting.
Same posture as `services/sentinel/onchain.py` and the reputation
anchor gate.
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

_log = structlog.get_logger(__name__)

_RECEIPT_TIMEOUT_SEC = 120


# `function exactInputSingle((address,address,address,uint256,uint256,uint256,uint160))`
# 4-byte selector for the mock + real Algebra V3.
_EXACT_INPUT_SINGLE_SELECTOR = keccak(
    b"exactInputSingle((address,address,address,uint256,uint256,uint256,uint160))"
)[:4]

# Uniswap V3 SwapRouter02 has a *different* tuple layout — fee tier
# instead of recipient-before-deadline ordering, and a `sqrtPriceLimitX96`
# field. Phase-5 momentum-on-Base uses this selector directly against the
# canonical V3 router (`0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4`).
# Reference: Uniswap V3 periphery `ISwapRouter.exactInputSingle` —
# `(address tokenIn, address tokenOut, uint24 fee, address recipient,
#  uint256 deadline, uint256 amountIn, uint256 amountOutMinimum,
#  uint160 sqrtPriceLimitX96)`.
_UNISWAP_V3_EXACT_INPUT_SINGLE_SELECTOR = keccak(
    b"exactInputSingle((address,address,uint24,address,uint256,uint256,uint256,uint160))"
)[:4]

# IERC20.approve(address,uint256) — vault gates each trade call on
# selector, and the router needs an allowance before its transferFrom
# inside the swap.
_APPROVE_SELECTOR = keccak(b"approve(address,uint256)")[:4]


def _build_approve_calldata(spender: str, amount: int) -> bytes:
    return _APPROVE_SELECTOR + _addr_word(spender) + amount.to_bytes(32, "big")


@dataclass(frozen=True, slots=True)
class TradeCall:
    """Mirrors `IStrategyVault.Call`. Single-router Phase 1, but the
    StrategyVault loop iterates so the executor stays general."""

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
    """One pending or submitted execution. The runtime keeps an
    in-memory list for tests + observability before WS3 wires real
    transactions."""

    plan: ExecutionPlan
    submitted: bool = False
    tx_hash: str = ""
    error: str = ""
    extras: dict[str, Any] = field(default_factory=dict)


class TradeExecutor:
    """Encodes + submits one swap per signal.

    `venue_kind` selects the calldata shape. `"algebra"` (default,
    Kite + the SDK's MockSwapRouter fallback) emits the seven-word
    Algebra Integral tuple; `"uniswap_v3"` (Phase-5 Base Sepolia)
    emits the eight-word V3 SwapRouter02 tuple with `fee` +
    `sqrtPriceLimitX96`. The pool fee tier is read from
    `pool_fee_bps` (in hundredths of a bp — UniV3's canonical
    `uint24 fee`, e.g. 500 = 0.05%, 3000 = 0.3%, 10000 = 1%).
    Algebra has no fee tier (single dynamic fee), so `pool_fee_bps`
    is ignored on that path."""

    def __init__(
        self,
        rpc_url: str,
        operator_pk: str,
        strategy_vault_address: str,
        mock_router_address: str,
        chain_id: int,
        deadline_buffer_sec: int = 120,
        *,
        venue_kind: str = "algebra",
        pool_fee_bps: int = 500,
    ) -> None:
        if venue_kind not in {"algebra", "uniswap_v3"}:
            raise ValueError(f"unknown venue_kind: {venue_kind}")
        self._rpc_url = rpc_url
        self._operator_pk = operator_pk
        self._vault = strategy_vault_address
        self._router = mock_router_address
        self._chain_id = chain_id
        self._deadline_buffer = deadline_buffer_sec
        self._venue_kind = venue_kind
        self._pool_fee_bps = pool_fee_bps
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
        Callers that need to read on-chain state for NAV seeding can
        opt into `_ensure_live()` themselves and read this back."""
        if self._w3 is None and self._live:
            self._ensure_live()
        return self._w3

    @property
    def venue_kind(self) -> str:
        return self._venue_kind

    @property
    def pool_fee_bps(self) -> int:
        return self._pool_fee_bps

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
        """Encode `exactInputSingle` calldata for MockSwapRouter / Algebra.

        Hand-rolled ABI encoder: 7 fixed-width 32-byte words, no
        dynamic types — keeps the Phase 1 dep tree free of `eth-abi`'s
        full encoder. Wider tuples / dynamic strings would need a real
        encoder; we'll bring one in when Algebra's real router exposes
        a multi-hop path.
        """
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

    def build_uniswap_v3_calldata(
        self,
        *,
        token_in: str,
        token_out: str,
        recipient: str,
        amount_in: int,
        amount_out_minimum: int,
        deadline_unix: int,
        fee: int | None = None,
    ) -> bytes:
        """Encode `exactInputSingle` calldata for the canonical Uniswap
        V3 SwapRouter02 deployment on Base Sepolia.

        Tuple layout (from `ISwapRouter.ExactInputSingleParams`):
          `(address tokenIn, address tokenOut, uint24 fee,
           address recipient, uint256 deadline, uint256 amountIn,
           uint256 amountOutMinimum, uint160 sqrtPriceLimitX96)`

        Eight 32-byte words behind the V3 selector — different field
        order from Algebra's seven-word tuple, plus a fee tier slot.
        Hand-rolled to keep the dep tree minimal; see the module
        docstring on `_addr_word` for the address-to-word convention.
        """
        fee_tier = fee if fee is not None else self._pool_fee_bps
        words = [
            _addr_word(token_in),
            _addr_word(token_out),
            int(fee_tier).to_bytes(32, "big"),
            _addr_word(recipient),
            deadline_unix.to_bytes(32, "big"),
            amount_in.to_bytes(32, "big"),
            amount_out_minimum.to_bytes(32, "big"),
            (0).to_bytes(32, "big"),  # sqrtPriceLimitX96 = 0 ⇒ no limit
        ]
        return _UNISWAP_V3_EXACT_INPUT_SINGLE_SELECTOR + b"".join(words)

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
        recipient = self._vault or "0x" + "0" * 40
        if self._venue_kind == "uniswap_v3":
            swap_data = self.build_uniswap_v3_calldata(
                token_in=token_in,
                token_out=token_out,
                recipient=recipient,
                amount_in=amount_in,
                amount_out_minimum=min_amount_out,
                deadline_unix=deadline_unix,
            )
        else:
            swap_data = self.build_swap_calldata(
                token_in=token_in,
                token_out=token_out,
                recipient=recipient,
                amount_in=amount_in,
                amount_out_minimum=min_amount_out,
                deadline_unix=deadline_unix,
            )
        approve_data = _build_approve_calldata(self._router, amount_in)
        return ExecutionPlan(
            proof=proof,
            public_inputs=list(public_inputs),
            trades=[
                TradeCall(target=token_in, value=0, data=approve_data),
                TradeCall(target=self._router, value=0, data=swap_data),
            ],
        )

    # ── Submission ────────────────────────────────────────────
    def submit(self, plan: ExecutionPlan, **extras: Any) -> ExecutionRecord:
        record = ExecutionRecord(plan=plan, extras=dict(extras))
        if not self._live:
            self.pending.append(record)
            _log.info(
                "momentum.exec.dry_run",
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
            _log.error("momentum.exec.submit_failed", vault=self._vault, err=str(exc))
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
        """Submit `StrategyVault.reportNAV(signedNAV)`.

        `signedNAV = abi.encode(uint256 totalNAV, uint64 timestamp, bytes signature)`,
        with the signature recovering to `navOracle` over
        `keccak256(abi.encode(vault, totalNAV, timestamp))` (no EIP-191
        prefix, per StrategyVault.sol). Phase 1 records, doesn't submit.
        """
        plan = ExecutionPlan(
            proof=b"",
            public_inputs=[],
            trades=[],
        )
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
                extras={
                    **record.extras,
                    "block": block_number,
                },
            )
        except Exception as exc:
            record = ExecutionRecord(
                plan=plan, submitted=False, error=str(exc), extras=record.extras
            )
            _log.error("momentum.nav.submit_failed", vault=self._vault, err=str(exc))
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
                # 2× headroom so Arb/Base base-fee drift between estimate
                # and inclusion doesn't reject the tx (see yr executor).
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

    def _submit_execute_with_proof(self, plan: ExecutionPlan) -> tuple[str, int]:
        self._ensure_live()
        assert self._vault_contract is not None
        # `Call[]` is `(address,uint256,bytes)[]`; web3 accepts dicts or tuples.
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
        # StrategyVault.reportNAV expects `signedNAV = abi.encode(uint256, uint64, bytes)`.
        signed_nav = abi_encode(
            ["uint256", "uint64", "bytes"], [total_nav_e18, timestamp, signature]
        )
        fn = self._vault_contract.functions.reportNAV(signed_nav)
        return self._send(fn)


def _addr_word(addr: str) -> bytes:
    """Pad a hex address into a 32-byte big-endian word.

    Accepts symbols too (e.g. "USDC") for unit tests / scenario mode —
    they get hashed-truncated to 20 bytes so the encoder stays
    address-shaped without forcing all callers to mint testnet tokens.
    """
    if addr.startswith("0x") or addr.startswith("0X"):
        raw = bytes.fromhex(addr[2:].rjust(40, "0"))
    else:
        raw = keccak(addr.encode("utf-8"))[-20:]
    return b"\x00" * 12 + raw
