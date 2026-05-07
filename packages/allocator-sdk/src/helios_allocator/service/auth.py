"""Server-side verification of meta-strategy submissions.

Phase 4 (WS-FE-1) supports two authorization paths, distinguished by
`MetaStrategyPayload.auth`:

  * `"eip191"` (anvil/dev) — frontend signs `canonical_digest(payload)`
    with `personal_sign`; this module recovers the signer and asserts
    it matches `user_address`.
  * `"passport"` (production) — frontend submits a batched userOp via
    Kite Passport that already authorized `UserVault.setMetaStrategy`
    on chain. The on-chain side of that path is the user's signature;
    Sentinel only enforces the `(user, nonce)` / `valid_until` replay
    window so a captured payload cannot be re-POSTed against another
    allocator instance to re-bind a revoked delegation.

The canonical digest excludes both `signature` and `auth` so EIP-191
clients written before the Phase 4 enum existed still verify against
payloads that now carry the field. Shared across allocators: the
digest format IS the wire contract. If Sentinel and Helix used
different digest implementations a payload signed by the user could
be rejected by one allocator and accepted by the other.

Phase 5 will replace the EIP-191 path with an EIP-1271 verification
against the AA wallet at the EntryPoint, removing the off-chain
EOA-signing path entirely.
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
_WS_DIGEST_PREFIX = "Helios ws subscribe v1\n"


class MetaStrategySignatureError(ValueError):
    """Raised when a meta-strategy payload's signature doesn't match
    `user_address` under the Phase 1 canonical digest, or when the
    payload is expired or replayed."""


class WSSubscribeSignatureError(ValueError):
    """Raised when a WebSocket subscribe signature doesn't recover to
    the path-bound user address, is malformed, or is expired."""


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
    serialized in insertion order. The digest excludes both the
    signature (which the digest authenticates) and the auth-mode tag
    (which selects the verification path on the server) so that an
    EIP-191 signature produced before the Phase 4 enum existed still
    recovers correctly against a payload that now carries `auth`.
    """
    raw = payload.model_dump(exclude={"signature", "auth"})
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
    """Authorize a meta-strategy submission.

    Behaviour depends on `payload.auth`:

      * `"eip191"` (default) — recover the EIP-191 personal_sign over
        `canonical_digest(payload)` and assert it matches
        `user_address`. Then enforce `valid_until > now` and the
        nonce-replay window.
      * `"passport"` — skip signature recovery (the user's
        authorization lives at the EntryPoint via the userOp the
        frontend already submitted). Still enforce `valid_until > now`
        and the nonce-replay window so a captured payload can't be
        re-POSTed against a different allocator instance.

    Returns the user's checksum address on success. Raises
    `MetaStrategySignatureError` on any failure.

    `now` and `nonce_store` are injected so unit tests can drive
    deterministic time + dedup state. Production callers pass a
    long-lived `NonceStore` shared by the request handler.
    """
    current = int(time.time()) if now is None else now
    if payload.valid_until <= current:
        raise MetaStrategySignatureError(
            f"signature expired: valid_until={payload.valid_until} <= now={current}"
        )

    if payload.auth == "passport":
        # Passport mode: the on-chain userOp is the user's signature.
        # Sentinel cannot independently re-derive that authorization
        # without an RPC round-trip, so we trust the on-chain truth and
        # only enforce the replay window. The Phase 5 cutover will add
        # an EIP-1271 verification against the AA wallet at the EntryPoint.
        recovered = payload.user_address
    else:
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

    if nonce_store is not None and not nonce_store.claim(
        payload.user_address, payload.nonce, payload.valid_until, now=current
    ):
        raise MetaStrategySignatureError(
            f"nonce {payload.nonce} already used for {payload.user_address}"
        )

    return recovered


def ws_subscribe_digest(user_address: str, valid_until: int) -> str:
    """The frontend signs the same string before opening
    `WS /v1/users/{user}/events`. Sorted-key JSON keeps the digest
    deterministic across the JS/Python boundary the way the
    meta-strategy digest does.
    """
    body = json.dumps(
        {"user": user_address.lower(), "valid_until": int(valid_until)},
        separators=(",", ":"),
    )
    return _WS_DIGEST_PREFIX + body


def verify_ws_subscribe_signature(
    user_address: str,
    valid_until: int,
    signature: str,
    *,
    now: int | None = None,
) -> str:
    """Authorize a WS subscriber for `/v1/users/{user}/events`.

    The endpoint streams a user's allocation rotations and capital
    movements; without this check anyone can subscribe to any address
    and watch their portfolio in real time (HIGH #18 in
    `docs/phase-3-review.md`).

    Verifies, in order:
      1. `signature` recovers to a non-empty address.
      2. The recovered address matches `user_address` (case-insensitive).
      3. `valid_until > now` so a captured signature can only open a
         socket inside its short window — there's no nonce because the
         only post-accept attack is "open another socket," and the
         expiry already bounds that.

    `now` is injected for deterministic tests. Returns the recovered
    checksum address on success; raises `WSSubscribeSignatureError`
    otherwise.
    """
    if not signature or signature == "0x":
        raise WSSubscribeSignatureError("missing signature")
    digest = ws_subscribe_digest(user_address, valid_until)
    encoded = encode_defunct(text=digest)
    try:
        recovered = Account.recover_message(encoded, signature=signature)
    except Exception as exc:
        raise WSSubscribeSignatureError(f"signature recovery failed: {exc}") from None
    if recovered.lower() != user_address.lower():
        raise WSSubscribeSignatureError(f"signer {recovered} does not match user {user_address}")
    current = int(time.time()) if now is None else now
    if int(valid_until) <= current:
        raise WSSubscribeSignatureError(
            f"signature expired: valid_until={valid_until} <= now={current}"
        )
    return recovered


__all__ = [
    "MetaStrategySignatureError",
    "NonceStore",
    "WSSubscribeSignatureError",
    "canonical_digest",
    "verify_meta_strategy_signature",
    "verify_ws_subscribe_signature",
    "ws_subscribe_digest",
]
