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

Replay protection: every payload carries a fresh 64-bit `nonce` minted
by the frontend. Verification enforces (a) `valid_until > now` so an
expired signature cannot be replayed, and (b) per-user nonce dedup
through an injected `NonceStore` so a captured payload cannot be
re-submitted before it expires. Without both checks a captured
signature could indefinitely re-bind a delegation the user revoked
off-chain.

The Phase 4 Passport rebuild (`docs/kite-passport-notes.md §"Migration
plan"`) replaces the EOA `personal_sign` with an AA userOp signature
verified at the EntryPoint; until then the `[PASSPORT-STUB]` server
verifier closes the open hole that the unsigned-write path exposes.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from eth_account import Account
from eth_account.messages import encode_defunct

from helios_allocator.service.schemas import MetaStrategyPayload

_DIGEST_PREFIX = "Helios meta-strategy v1\n"


class MetaStrategySignatureError(ValueError):
    """Raised when a meta-strategy payload's signature doesn't match
    `user_address` under the Phase 1 canonical digest, or when the
    payload is expired or replayed."""


@dataclass
class NonceStore:
    """In-process replay-protection cache.

    Tracks `(user_address_lower, nonce) -> valid_until`. `claim` returns
    True the first time a (user, nonce) pair is seen and False on any
    subsequent attempt. Entries whose `valid_until` has passed are
    evicted lazily so the store doesn't grow forever; a single allocator
    process plus a finite `valid_until` window keeps memory bounded.

    Single-process is sufficient for Phase 3 (each allocator service is
    a single PM2 worker). A multi-replica deployment would back this
    with Postgres or Redis using the same interface — see the Phase 5
    migration note in `docs/phase-3-review.md`.
    """

    _seen: dict[tuple[str, int], int] = field(default_factory=dict)

    def claim(self, user_address: str, nonce: int, valid_until: int, *, now: int) -> bool:
        """Atomically: evict stale, then record-or-reject this nonce.

        Returns True iff the (user, nonce) pair has not been seen yet
        under any unexpired entry. False indicates a replay.
        """
        self._evict_expired(now)
        key = (user_address.lower(), nonce)
        if key in self._seen:
            return False
        self._seen[key] = valid_until
        return True

    def _evict_expired(self, now: int) -> None:
        # Materialize the doomed list before mutating to avoid
        # iterator invalidation; eviction cost is amortized across
        # claim() calls so a slow trickle of stale entries is fine.
        stale = [k for k, exp in self._seen.items() if exp <= now]
        for k in stale:
            del self._seen[k]

    def __len__(self) -> int:
        return len(self._seen)


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


def verify_meta_strategy_signature(
    payload: MetaStrategyPayload,
    *,
    now: int | None = None,
    nonce_store: NonceStore | None = None,
) -> str:
    """Recover the signer of `payload.signature` against `payload.user_address`.

    Enforces, in order:
      1. Signature recovery succeeds and matches `user_address`.
      2. `payload.valid_until > now` (signature is not expired).
      3. If `nonce_store` is provided, `payload.nonce` has not been seen
         under this user before within an unexpired window.

    Returns the recovered checksum address on success. Raises
    `MetaStrategySignatureError` on any failure.

    `now` and `nonce_store` are injected so unit tests can drive
    deterministic time + dedup state. Production callers pass a
    long-lived `NonceStore` shared by the request handler.
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

    current = int(time.time()) if now is None else now
    if payload.valid_until <= current:
        raise MetaStrategySignatureError(
            f"signature expired: valid_until={payload.valid_until} <= now={current}"
        )

    if nonce_store is not None and not nonce_store.claim(
        payload.user_address, payload.nonce, payload.valid_until, now=current
    ):
        raise MetaStrategySignatureError(
            f"nonce {payload.nonce} already used for {payload.user_address}"
        )

    return recovered


__all__ = [
    "MetaStrategySignatureError",
    "NonceStore",
    "canonical_digest",
    "verify_meta_strategy_signature",
]
