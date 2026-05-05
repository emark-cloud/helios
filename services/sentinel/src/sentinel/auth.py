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
    canonical_digest,
    verify_meta_strategy_signature,
)

__all__ = [
    "MetaStrategySignatureError",
    "canonical_digest",
    "verify_meta_strategy_signature",
]
