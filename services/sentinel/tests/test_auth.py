"""Server-side verification of `[PASSPORT-STUB]` signatures.

Bit-exact against the frontend's `OnboardClient.tsx::canonicalDigest`:
sorted keys, no whitespace, prefix `"Helios meta-strategy v1\\n"`,
EIP-191 personal_sign envelope.
"""

from __future__ import annotations

import json

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from sentinel.auth import (
    MetaStrategySignatureError,
    canonical_digest,
    verify_meta_strategy_signature,
)
from sentinel.schemas import MetaStrategyPayload

_PK = "0x" + "11" * 32  # well-known test key


def _payload(**overrides: object) -> MetaStrategyPayload:
    user = Account.from_key(_PK).address
    base: dict[str, object] = {
        "user_address": user,
        "allowed_strategy_classes": ["momentum_v1"],
        "allowed_assets": ["USDC", "WKITE"],
        "allowed_chains": [2368],
        "max_capital_usd": 10_000,
        "max_per_strategy_bps": 5_000,
        "max_strategies_count": 2,
        "drawdown_threshold_bps": 1_500,
        "max_fee_rate_bps": 2_500,
        "rebalance_cadence_sec": 900,
        "valid_until": 2_000_000_000,
    }
    base.update(overrides)
    return MetaStrategyPayload.model_validate(base)


def _sign(payload: MetaStrategyPayload, pk: str = _PK) -> str:
    digest = canonical_digest(payload)
    encoded = encode_defunct(text=digest)
    return Account.sign_message(encoded, pk).signature.hex()


def test_canonical_digest_is_sorted_and_compact() -> None:
    p = _payload()
    digest = canonical_digest(p)
    assert digest.startswith("Helios meta-strategy v1\n")
    body = json.loads(digest.split("\n", 1)[1])
    assert list(body.keys()) == sorted(body.keys())
    # Verify the body has no whitespace (compact json) by reserializing.
    assert "\n" not in digest.split("\n", 1)[1]
    assert ", " not in digest


def test_verify_round_trip() -> None:
    p = _payload()
    p = p.model_copy(update={"signature": _sign(p)})
    recovered = verify_meta_strategy_signature(p)
    assert recovered.lower() == p.user_address.lower()


def test_verify_rejects_empty_stub() -> None:
    p = _payload(signature="0x")
    with pytest.raises(MetaStrategySignatureError, match="missing"):
        verify_meta_strategy_signature(p)


def test_verify_rejects_signer_mismatch() -> None:
    p = _payload()
    other_pk = "0x" + "22" * 32
    p = p.model_copy(update={"signature": _sign(p, pk=other_pk)})
    with pytest.raises(MetaStrategySignatureError, match="does not match"):
        verify_meta_strategy_signature(p)


def test_verify_rejects_tampered_payload() -> None:
    p = _payload()
    sig = _sign(p)
    # Body tampered after the user signed: max_capital bumped 10x.
    tampered = p.model_copy(update={"signature": sig, "max_capital_usd": 100_000})
    with pytest.raises(MetaStrategySignatureError, match="does not match"):
        verify_meta_strategy_signature(tampered)


def test_verify_rejects_malformed_signature() -> None:
    p = _payload(signature="0xnothex")
    with pytest.raises(MetaStrategySignatureError, match="recovery failed"):
        verify_meta_strategy_signature(p)
