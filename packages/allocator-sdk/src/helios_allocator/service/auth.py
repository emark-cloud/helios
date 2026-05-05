"""Server-side verification of `[PASSPORT-STUB]` meta-strategy signatures.

The frontend (`frontend/src/components/onboard/OnboardClient.tsx`) calls
`personal_sign` over a stable canonical digest:

    "Helios meta-strategy v1\\n" + JSON.stringify(<sorted payload sans signature>)

This module reproduces that digest and recovers the signer via EIP-191
`personal_sign`. A mismatch → 401 at the REST boundary.

Shared across allocators: the digest format IS the wire contract. If
Sentinel and Helix used different digest implementations a payload
signed by the user could be rejected by one allocator and accepted by
the other — a class of bug we close by keeping a single canonical
implementation here in the SDK.

The Phase 4 Passport rebuild (`docs/kite-passport-notes.md §"Migration
plan"`) replaces the EOA `personal_sign` with an AA userOp signature
verified at the EntryPoint; until then the `[PASSPORT-STUB]` server
verifier closes the open hole that the unsigned-write path exposes.
"""

from __future__ import annotations

import json
from typing import Any

from eth_account import Account
from eth_account.messages import encode_defunct

from helios_allocator.service.schemas import MetaStrategyPayload

_DIGEST_PREFIX = "Helios meta-strategy v1\n"


class MetaStrategySignatureError(ValueError):
    """Raised when a meta-strategy payload's signature doesn't match
    `user_address` under the Phase 1 canonical digest."""


def canonical_digest(payload: MetaStrategyPayload) -> str:
    """Reproduce the digest produced by `OnboardClient.tsx::canonicalDigest`.

    Stable JSON: keys sorted lexicographically, no whitespace, sequences
    serialized in insertion order.
    """
    raw = payload.model_dump(exclude={"signature"})
    ordered_keys = sorted(raw.keys())
    body: dict[str, Any] = {k: _coerce(raw[k]) for k in ordered_keys}
    return _DIGEST_PREFIX + json.dumps(body, separators=(",", ":"))


def _coerce(value: Any) -> Any:
    if isinstance(value, tuple | list):
        return [_coerce(v) for v in value]
    return value


def verify_meta_strategy_signature(payload: MetaStrategyPayload) -> str:
    """Recover the signer of `payload.signature` against `payload.user_address`.

    Returns the recovered checksum address on success. Raises
    `MetaStrategySignatureError` on any failure (malformed signature,
    mismatch, empty stub).
    """
    sig = payload.signature
    if not sig or sig == "0x":
        raise MetaStrategySignatureError("missing signature")
    digest = canonical_digest(payload)
    encoded = encode_defunct(text=digest)
    try:
        recovered = Account.recover_message(encoded, signature=sig)
    except Exception as exc:  # malformed hex, wrong length, etc.
        raise MetaStrategySignatureError(f"signature recovery failed: {exc}") from None
    if recovered.lower() != payload.user_address.lower():
        raise MetaStrategySignatureError(
            f"signer {recovered} does not match user_address {payload.user_address}"
        )
    return recovered


__all__ = [
    "MetaStrategySignatureError",
    "canonical_digest",
    "verify_meta_strategy_signature",
]
