"""EIP-712 signer for ReputationAnchor.postReputationUpdate.

Mirrors the `_UPDATE_TYPEHASH` and EIP-712 domain in
`contracts/src/ReputationAnchor.sol`:

    domain = ("HeliosReputationAnchor", "1", chainId, anchorAddress)
    typehash = keccak256(
      "ReputationUpdate(address actor,uint8 actorType,int256 currentScore,"
      "uint256 lastUpdateBlock,uint256 totalAttestedTrades,"
      "uint256 totalRealizedPnL,uint256 maxDrawdownBps,"
      "uint256 proofValidityRateBps)"
    )

If `signer_pk` is unset (e.g. local dev with no anchor deployed), `sign_update`
returns a 65-byte zero placeholder so the caller can still log the payload
shape; the on-chain post will revert with InvalidSigner. Production deploy
must set REPUTATION_SIGNER_PK.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from eth_account import Account
from eth_account.messages import encode_typed_data


class ActorType(IntEnum):
    STRATEGY = 0
    ALLOCATOR = 1


@dataclass(frozen=True, slots=True)
class ReputationUpdate:
    actor: str  # 0x... address
    actor_type: ActorType
    current_score: int  # int256, [-10_000, +10_000]
    last_update_block: int
    total_attested_trades: int
    total_realized_pnl: int  # uint256 (signed semantics enforced by score formula)
    max_drawdown_bps: int
    proof_validity_rate_bps: int


@dataclass(frozen=True, slots=True)
class SignedUpdate:
    update: ReputationUpdate
    signature: bytes
    signer: str


_DOMAIN_NAME = "HeliosReputationAnchor"
_DOMAIN_VERSION = "1"
_TYPES = {
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


class ReputationSigner:
    def __init__(self, private_key_hex: str, chain_id: int, anchor_address: str) -> None:
        self._chain_id = chain_id
        self._anchor = anchor_address
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

    def _domain(self) -> dict[str, object]:
        return {
            "name": _DOMAIN_NAME,
            "version": _DOMAIN_VERSION,
            "chainId": self._chain_id,
            "verifyingContract": self._anchor,
        }

    def sign_update(self, update: ReputationUpdate) -> SignedUpdate:
        if self._account is None:
            return SignedUpdate(update=update, signature=b"\x00" * 65, signer=self._address)
        message = {
            "actor": update.actor,
            "actorType": int(update.actor_type),
            "currentScore": update.current_score,
            "lastUpdateBlock": update.last_update_block,
            "totalAttestedTrades": update.total_attested_trades,
            "totalRealizedPnL": update.total_realized_pnl,
            "maxDrawdownBps": update.max_drawdown_bps,
            "proofValidityRateBps": update.proof_validity_rate_bps,
        }
        encoded = encode_typed_data(
            domain_data=self._domain(),
            message_types=_TYPES,
            message_data=message,
        )
        signed = self._account.sign_message(encoded)
        return SignedUpdate(update=update, signature=signed.signature, signer=self._address)
