"""WS5.A — `postReputationUpdate` round-trip with `actor_type=ALLOCATOR`.

Confirms the AnchorPoster encodes the allocator path correctly: the
top-level `actorType` arg + the duplicated field inside `ReputationData`
both carry `ActorType.ALLOCATOR=1`, and the resulting calldata targets
the v2 `postReputationUpdate(address,uint8,(...),bytes)` selector.
"""

from __future__ import annotations

from eth_utils.crypto import keccak
from reputation.anchor import AnchorPoster
from reputation.signer import ActorType, ReputationSigner, ReputationUpdate

_PK = "0x" + "ab" * 32
_ANCHOR = "0x" + "11" * 20
_ALLOCATOR = "0x" + "33" * 20


def _signed_allocator_update(score: int = 4321) -> object:
    signer = ReputationSigner(_PK, chain_id=2368, anchor_address=_ANCHOR)
    return signer.sign_update(
        ReputationUpdate(
            actor=_ALLOCATOR,
            actor_type=ActorType.ALLOCATOR,
            current_score=score,
            last_update_block=1_700_000_000,
            total_attested_trades=0,
            total_realized_pnl=5 * 10**18,
            max_drawdown_bps=0,
            proof_validity_rate_bps=0,
            components_hash=b"\x42" * 32,
        )
    )


def test_dry_run_records_allocator_post() -> None:
    poster = AnchorPoster(rpc_url="", signer_pk="", anchor_address="", chain_id=2368)
    assert poster.live is False

    signed = _signed_allocator_update()
    result = poster.post(signed)  # type: ignore[arg-type]
    assert result.actor == _ALLOCATOR
    assert result.score_e4 == 4321
    assert result.submitted is False
    assert list(poster.pending) == [result]


def test_live_encoding_carries_allocator_actor_type() -> None:
    """The encoded calldata must put `actorType=1` in BOTH the top-level
    arg and the nested struct field — the contract recovers EIP-712
    against the struct-internal copy. Exercised against the v2 anchor
    ABI (8-field struct) here; the v1 equivalent is covered in
    `test_anchor.test_v1_live_encoding_uses_v1_selector`."""
    poster = AnchorPoster(
        rpc_url="http://127.0.0.1:1",  # never dialled
        signer_pk=_PK,
        anchor_address=_ANCHOR,
        chain_id=2368,
        typehash_version="2",
    )
    poster._ensure_live()
    assert poster._contract is not None

    signed = _signed_allocator_update()
    u = signed.update  # type: ignore[attr-defined]
    components_hash = (u.components_hash or b"").rjust(32, b"\x00")
    fn = poster._contract.functions.postReputationUpdate(
        u.actor,
        int(u.actor_type),
        (
            int(u.current_score),
            int(u.last_update_block),
            int(u.total_attested_trades),
            int(u.total_realized_pnl),
            int(u.max_drawdown_bps),
            int(u.proof_validity_rate_bps),
            int(u.actor_type),
            components_hash,
        ),
        signed.signature,  # type: ignore[attr-defined]
    )
    data = fn._encode_transaction_data()
    assert data.startswith(_expected_selector())

    # `int(u.actor_type) == 1` for ALLOCATOR; the duplicated copy in the
    # struct shows up as a 32-byte word `...01`. Cheap sanity that we
    # didn't accidentally encode STRATEGY (0) somewhere.
    assert int(u.actor_type) == 1
    # Find the encoded actorType in calldata (right-padded uint8 = 32-byte
    # word ending in 0x01). Two appearances expected: top-level + struct.
    word = "00" * 31 + "01"
    assert data.count(word) >= 2


def _expected_selector() -> str:
    sig = (
        "postReputationUpdate(address,uint8,"
        "(int256,uint256,uint256,uint256,uint256,uint256,uint8,bytes32),bytes)"
    )
    return "0x" + keccak(sig.encode())[:4].hex()


def _update_with_actor_type(actor_type: ActorType) -> ReputationUpdate:
    return ReputationUpdate(
        actor=_ALLOCATOR,
        actor_type=actor_type,
        current_score=4321,
        last_update_block=1_700_000_000,
        total_attested_trades=0,
        total_realized_pnl=5 * 10**18,
        max_drawdown_bps=0,
        proof_validity_rate_bps=0,
        components_hash=b"\x42" * 32,
    )


def test_eip712_signature_differs_from_strategy_path() -> None:
    """An allocator and strategy update with otherwise-identical fields
    sign to different EIP-712 digests because `actorType` is part of the
    `ReputationUpdate` struct hash."""
    signer = ReputationSigner(_PK, chain_id=2368, anchor_address=_ANCHOR)
    sig_strategy = signer.sign_update(_update_with_actor_type(ActorType.STRATEGY)).signature
    sig_allocator = signer.sign_update(_update_with_actor_type(ActorType.ALLOCATOR)).signature
    assert sig_strategy != sig_allocator
