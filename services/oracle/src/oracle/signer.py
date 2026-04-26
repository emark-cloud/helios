"""ECDSA signer for oracle snapshots.

Snapshots are signed via `eth_account` over the message digest:

    keccak256(abi.encode(asset_id, price_e18, timestamp_ms))

`asset_id` is hashed first (`keccak256(asset_string)`) so the on-chain
verifier can pre-image the asset by symbol without dealing with variable
strings.

The signer key is loaded from `ORACLE_SIGNER_PK` (hex, with or without
`0x`). If unset (e.g. tests), `LocalSigner.signer_address` returns the
zero address and `sign()` returns a deterministic 65-byte placeholder so
downstream code doesn't have to fork on a missing key.
"""

from __future__ import annotations

from dataclasses import dataclass

from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils.crypto import keccak


@dataclass(frozen=True, slots=True)
class SignedDigest:
    digest: bytes  # 32-byte keccak digest
    signature: bytes  # 65-byte recoverable signature
    signer: str  # hex 0x... address (or "0x000...0" when unsigned)


class LocalSigner:
    def __init__(self, private_key_hex: str = "") -> None:
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

    def sign_quote(self, asset: str, price_e18: int, timestamp_ms: int) -> SignedDigest:
        asset_hash = keccak(asset.encode("utf-8"))
        # abi.encode of (bytes32, uint256, uint256) — mirror the shape
        # OraclePriceAnchor.sol will recover under in Phase 2+. abi.encode
        # is just left-padded 32-byte words concatenated, no length prefix
        # for fixed types.
        body = asset_hash + price_e18.to_bytes(32, "big") + timestamp_ms.to_bytes(32, "big")
        digest = keccak(body)
        if self._account is None:
            return SignedDigest(digest=digest, signature=b"\x00" * 65, signer=self._address)
        # Sign via personal_sign-style EIP-191 framing so a Solidity verifier
        # using `ecrecover` over the eth-message prefix will recover correctly.
        message = encode_defunct(primitive=digest)
        signed = self._account.sign_message(message)
        return SignedDigest(
            digest=digest,
            signature=signed.signature,
            signer=self._address,
        )
