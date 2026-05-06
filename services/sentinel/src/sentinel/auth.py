"""Sentinel re-exports the shared meta-strategy signature verifier.

The canonical digest IS a wire contract between the frontend's
`personal_sign` call and every allocator service that accepts a
delegation. WS3.A moved the implementation into
`helios_allocator.service.auth` so Sentinel and Helix run the byte-
identical verifier; this module re-exports for back-compat with
existing imports.
"""

from __future__ import annotations

from helios_allocator.service.auth import (
    MetaStrategySignatureError,
    NonceStore,
    WSSubscribeSignatureError,
    canonical_digest,
    verify_meta_strategy_signature,
    verify_ws_subscribe_signature,
    ws_subscribe_digest,
)

__all__ = [
    "MetaStrategySignatureError",
    "NonceStore",
    "WSSubscribeSignatureError",
    "canonical_digest",
    "verify_meta_strategy_signature",
    "verify_ws_subscribe_signature",
    "ws_subscribe_digest",
]
