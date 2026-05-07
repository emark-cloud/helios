"""Service-layer primitives shared across allocator services.

Sentinel, Helix, and any third-party allocator scaffolded via
`helios-allocator init` all expose the same `/v1/users/{user}/...`
surface to the frontend. The meta-strategy digest is part of that
contract — divergence between allocators would silently reject
signatures cross-service. Pulling the canonical digest, signature
recovery, and request/response schemas here keeps that contract
single-sourced.

Phase 4 (WS-FE-1) introduced the `auth` enum on `MetaStrategyPayload`:
`"passport"` payloads skip EIP-191 verification (the userOp at the
EntryPoint is the user's authorization on chain) while `"eip191"`
payloads still verify the canonical digest signature. Both paths
enforce the `(user, nonce)` / `valid_until` replay window. Phase 5
will swap the EIP-191 path for an EIP-1271 verification against the
AA wallet.
"""

from helios_allocator.service.auth import (
    MetaStrategySignatureError,
    NonceStore,
    WSSubscribeSignatureError,
    canonical_digest,
    verify_meta_strategy_signature,
    verify_ws_subscribe_signature,
    ws_subscribe_digest,
)
from helios_allocator.service.schemas import (
    AllocationView,
    DashboardPayload,
    MetaStrategyPayload,
    StrategyDirectoryRow,
)

__all__ = [
    "AllocationView",
    "DashboardPayload",
    "MetaStrategyPayload",
    "MetaStrategySignatureError",
    "NonceStore",
    "StrategyDirectoryRow",
    "WSSubscribeSignatureError",
    "canonical_digest",
    "verify_meta_strategy_signature",
    "verify_ws_subscribe_signature",
    "ws_subscribe_digest",
]
