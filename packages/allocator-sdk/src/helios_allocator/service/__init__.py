"""Service-layer primitives shared across allocator services.

Sentinel, Helix, and any third-party allocator scaffolded via
`helios-allocator init` all expose the same `/v1/users/{user}/...`
surface to the frontend. The Phase 1 [PASSPORT-STUB] meta-strategy
digest is part of that contract — divergence between allocators would
silently reject signatures cross-service. Pulling the canonical
digest, signature recovery, and request/response schemas here keeps
that contract single-sourced.

Phase 4's Passport rebuild swaps `verify_meta_strategy_signature` for
AA-userOp verification at the EntryPoint; until then this module is
the verifier.
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
