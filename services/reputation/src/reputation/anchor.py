"""On-chain `ReputationAnchor.postReputationUpdate` submission.

Address-gated: when `REPUTATION_ANCHOR_ADDRESS` is unset, the poster
records what it *would have* submitted (`pending`) and returns. Same
posture as `services/sentinel/onchain.py` and the momentum executor —
keeps the engine path uniform across pre/post-deploy environments.

The signer key driving this submission is the same one the engine uses
to sign updates. `ReputationAnchor.postReputationUpdate` recovers the
EIP-712 signature against `reputationSigner`, so caller and signer must
agree. In Phase 1 e2e (Track A) we set both to the deployer key. In
Track B / production we set both to a dedicated `REPUTATION_SIGNER_PK`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog
from eth_account import Account
from helios_contracts_abi.abis import IReputationAnchor_ABI
from web3 import Web3
from web3.types import TxReceipt

from reputation.signer import SignedUpdate

_log = structlog.get_logger(__name__)
_RECEIPT_TIMEOUT_SEC = 30


@dataclass(slots=True)
class PostedUpdate:
    actor: str
    score_e4: int
    tx_hash: str = ""
    submitted: bool = False
    error: str = ""


class AnchorPoster:
    def __init__(
        self,
        rpc_url: str,
        signer_pk: str,
        anchor_address: str,
        chain_id: int,
    ) -> None:
        self._rpc_url = rpc_url
        self._signer_pk = signer_pk
        self._anchor = anchor_address
        self._chain_id = chain_id
        self._live = bool(rpc_url and signer_pk and anchor_address)
        self.pending: list[PostedUpdate] = []

        # Lazy live handles.
        self._w3: Web3 | None = None
        self._account: Any = None
        self._contract: Any = None

    @property
    def live(self) -> bool:
        return self._live

    def post(self, signed: SignedUpdate) -> PostedUpdate:
        result = PostedUpdate(actor=signed.update.actor, score_e4=signed.update.current_score)
        if not self._live:
            self.pending.append(result)
            _log.info(
                "reputation.anchor.dry_run",
                actor=signed.update.actor,
                score_e4=signed.update.current_score,
            )
            return result
        try:
            tx_hash, block_number = self._submit(signed)
            result.tx_hash = tx_hash
            result.submitted = True
            _log.info(
                "reputation.anchor.posted",
                actor=signed.update.actor,
                score_e4=signed.update.current_score,
                tx_hash=tx_hash,
                block=block_number,
            )
        except Exception as exc:
            result.error = str(exc)
            _log.error(
                "reputation.anchor.submit_failed",
                actor=signed.update.actor,
                err=str(exc),
            )
        self.pending.append(result)
        return result

    def _ensure_live(self) -> None:
        if self._w3 is not None:
            return
        self._w3 = Web3(Web3.HTTPProvider(self._rpc_url))
        pk = self._signer_pk if self._signer_pk.startswith("0x") else "0x" + self._signer_pk
        try:
            self._account = Account.from_key(pk)
        except Exception as exc:  # pragma: no cover — defensive
            # Don't let the raised value (which may include the malformed key
            # material) propagate up into structlog or a stack trace.
            raise RuntimeError(f"invalid REPUTATION_SIGNER_PK: {type(exc).__name__}") from None
        self._contract = self._w3.eth.contract(
            address=Web3.to_checksum_address(self._anchor),
            abi=IReputationAnchor_ABI,
        )

    def _submit(self, signed: SignedUpdate) -> tuple[str, int]:
        self._ensure_live()
        assert self._w3 is not None
        assert self._account is not None
        assert self._contract is not None

        u = signed.update
        # ReputationData struct (V2 schema, post-WS3.A — adds componentsHash):
        #   (currentScore, lastUpdateBlock, totalAttestedTrades,
        #    totalRealizedPnL, maxDrawdownBps, proofValidityRateBps,
        #    actorType, componentsHash). web3 takes a tuple in field order;
        # actorType is *also* a top-level arg per the function signature
        # (the duplicated field in the struct is what gets signed in the
        # EIP-712 typed payload). componentsHash is right-padded to bytes32.
        components_hash = u.components_hash if u.components_hash else b""
        if len(components_hash) > 32:
            raise ValueError("components_hash exceeds 32 bytes")
        components_hash_b32 = components_hash.rjust(32, b"\x00")
        data_tuple = (
            int(u.current_score),
            int(u.last_update_block),
            int(u.total_attested_trades),
            int(u.total_realized_pnl),
            int(u.max_drawdown_bps),
            int(u.proof_validity_rate_bps),
            int(u.actor_type),
            components_hash_b32,
        )
        fn = self._contract.functions.postReputationUpdate(
            Web3.to_checksum_address(u.actor),
            int(u.actor_type),
            data_tuple,
            signed.signature,
        )
        tx = fn.build_transaction(
            {
                "from": self._account.address,
                "nonce": self._w3.eth.get_transaction_count(self._account.address, "pending"),
                "chainId": self._chain_id,
                "gasPrice": self._w3.eth.gas_price,
            }
        )
        signed_tx = self._account.sign_transaction(tx)
        tx_hash = self._w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt: TxReceipt = self._w3.eth.wait_for_transaction_receipt(
            tx_hash, timeout=_RECEIPT_TIMEOUT_SEC
        )
        if receipt["status"] != 1:
            raise RuntimeError(f"tx reverted: {tx_hash.hex()}")
        return tx_hash.hex(), int(receipt["blockNumber"])


__all__ = ["AnchorPoster", "PostedUpdate"]
