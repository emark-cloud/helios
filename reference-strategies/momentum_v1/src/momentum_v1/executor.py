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
from eth_utils.crypto import keccak

_log = structlog.get_logger(__name__)


# `function exactInputSingle((address,address,address,uint256,uint256,uint256,uint160))`
# 4-byte selector for the mock + real Algebra V3.
_EXACT_INPUT_SINGLE_SELECTOR = keccak(
    b"exactInputSingle((address,address,address,uint256,uint256,uint256,uint160))"
)[:4]


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

    @property
    def live(self) -> bool:
        return self._live

    @property
    def vault(self) -> str:
        return self._vault

    @property
    def router(self) -> str:
        return self._router

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
                "momentum.exec.dry_run",
                vault=self._vault,
                trades=len(plan.trades),
                public_inputs_len=len(plan.public_inputs),
                proof_bytes=len(plan.proof),
            )
            return record
        # WS3 wires web3.py submission of executeWithProof. The encode
        # path is `selector || abi.encode(bytes proof, uint256[] PI,
        # Call[] trades)` and gets gas-priced via Kite testnet's RPC.
        raise NotImplementedError("live executeWithProof submission lands in WS3 e2e")

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
        raise NotImplementedError("live reportNAV submission lands in WS3 e2e")


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
