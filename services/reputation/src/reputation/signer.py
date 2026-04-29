"""EIP-712 signer for `ReputationAnchor.postReputationUpdate`.

Two typehashes coexist:

- **v1** (Phase 1, currently on-chain):
  ```
  ReputationUpdate(address actor,uint8 actorType,int256 currentScore,
                   uint256 lastUpdateBlock,uint256 totalAttestedTrades,
                   uint256 totalRealizedPnL,uint256 maxDrawdownBps,
                   uint256 proofValidityRateBps)
  ```
- **v2** (`docs/phase2-plan.md` WS3.A — adds `bytes32 componentsHash`):
  ```
  ReputationUpdate(address actor,uint8 actorType,int256 currentScore,
                   uint256 lastUpdateBlock,uint256 totalAttestedTrades,
                   uint256 totalRealizedPnL,uint256 maxDrawdownBps,
                   uint256 proofValidityRateBps,bytes32 componentsHash)
  ```

`REPUTATION_TYPEHASH_VERSION` (default `"1"`) selects which typehash + domain
version to sign. WS2.A lands the engine in shadow mode: scores compute with v2
inputs (componentsHash exposed via `/v1/audit`), but signing stays on v1 until
WS3.A's contract upgrade flips the flag.

Empty `signer_pk` returns a 65-byte zero placeholder so the engine can still
broadcast the payload shape pre-deploy (the on-chain post would revert with
`InvalidSigner`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

from eth_account import Account
from eth_account.messages import encode_typed_data


class ActorType(IntEnum):
    STRATEGY = 0
    ALLOCATOR = 1


@dataclass(frozen=True, slots=True)
class ReputationUpdate:
    actor: str
    actor_type: ActorType
    current_score: int
    last_update_block: int
    total_attested_trades: int
    total_realized_pnl: int
    max_drawdown_bps: int
    proof_validity_rate_bps: int
    # v2 only — ignored by v1 typehash. Empty bytes for v1-only callers.
    components_hash: bytes = field(default=b"")


@dataclass(frozen=True, slots=True)
class SignedUpdate:
    update: ReputationUpdate
    signature: bytes
    signer: str
    typehash_version: str  # "1" | "2"


_DOMAIN_NAME = "HeliosReputationAnchor"

_TYPES_V1 = {
    "ReputationUpdate": [
        {"name": "actor", "type": "address"},
        {"name": "actorType", "type": "uint8"},
        {"name": "currentScore", "type": "int256"},
        {"name": "lastUpdateBlock", "type": "uint256"},
        {"name": "totalAttestedTrades", "type": "uint256"},
        {"name": "totalRealizedPnL", "type": "uint256"},
        {"name": "maxDrawdownBps", "type": "uint256"},
        {"name": "proofValidityRateBps", "type": "uint256"},
    ]
}

_TYPES_V2 = {
    "ReputationUpdate": [
        *_TYPES_V1["ReputationUpdate"],
        {"name": "componentsHash", "type": "bytes32"},
    ]
}

# Backwards-compat alias used by `tests/test_signer.py` v1 path.
_DOMAIN_VERSION = "1"
_TYPES = _TYPES_V1


class ReputationSigner:
    def __init__(
        self,
        private_key_hex: str,
        chain_id: int,
        anchor_address: str,
        typehash_version: str = "1",
    ) -> None:
        if typehash_version not in {"1", "2"}:
            raise ValueError(f"unsupported typehash version: {typehash_version!r}")
        self._chain_id = chain_id
        self._anchor = anchor_address
        self._typehash_version = typehash_version
        if private_key_hex:
            pk = private_key_hex if private_key_hex.startswith("0x") else "0x" + private_key_hex
            self._account = Account.from_key(pk)
            self._address = self._account.address
        else:
            self._account = None
            self._address = "0x" + "0" * 40

    @property
    def signer_address(self) -> str:
        return self._address

    @property
    def typehash_version(self) -> str:
        return self._typehash_version

    def _domain(self) -> dict[str, object]:
        return {
            "name": _DOMAIN_NAME,
            "version": self._typehash_version,
            "chainId": self._chain_id,
            "verifyingContract": self._anchor,
        }

    def _types(self) -> dict[str, list[dict[str, str]]]:
        return _TYPES_V2 if self._typehash_version == "2" else _TYPES_V1

    def _message(self, update: ReputationUpdate) -> dict[str, object]:
        msg: dict[str, object] = {
            "actor": update.actor,
            "actorType": int(update.actor_type),
            "currentScore": update.current_score,
            "lastUpdateBlock": update.last_update_block,
            "totalAttestedTrades": update.total_attested_trades,
            "totalRealizedPnL": update.total_realized_pnl,
            "maxDrawdownBps": update.max_drawdown_bps,
            "proofValidityRateBps": update.proof_validity_rate_bps,
        }
        if self._typehash_version == "2":
            # bytes32 — left-pad short bytes to 32 so v2 still works when the
            # caller hasn't populated componentsHash (engine-internal default).
            ch = update.components_hash or b""
            if len(ch) > 32:
                raise ValueError("components_hash exceeds 32 bytes")
            msg["componentsHash"] = ch.rjust(32, b"\x00")
        return msg

    def sign_update(self, update: ReputationUpdate) -> SignedUpdate:
        if self._account is None:
            return SignedUpdate(
                update=update,
                signature=b"\x00" * 65,
                signer=self._address,
                typehash_version=self._typehash_version,
            )
        encoded = encode_typed_data(
            domain_data=self._domain(),
            message_types=self._types(),
            message_data=self._message(update),
        )
        signed = self._account.sign_message(encoded)
        return SignedUpdate(
            update=update,
            signature=signed.signature,
            signer=self._address,
            typehash_version=self._typehash_version,
        )
