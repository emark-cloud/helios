"""AnchorPoster unit tests — dry-run + live encoding."""

from __future__ import annotations

import pytest
from eth_utils.crypto import keccak
from reputation.anchor import AnchorPoster
from reputation.signer import ActorType, ReputationSigner, ReputationUpdate

_PK = "0x" + "ab" * 32
_ANCHOR = "0x" + "11" * 20
_ACTOR = "0x" + "22" * 20


def _signed_update(score: int = 1234) -> object:
    signer = ReputationSigner(_PK, chain_id=2368, anchor_address=_ANCHOR)
    return signer.sign_update(
        ReputationUpdate(
            actor=_ACTOR,
            actor_type=ActorType.STRATEGY,
            current_score=score,
            last_update_block=100,
            total_attested_trades=1,
            total_realized_pnl=10**18,
            max_drawdown_bps=0,
            proof_validity_rate_bps=10_000,
        )
    )


def test_dry_run_records_without_submitting() -> None:
    poster = AnchorPoster(rpc_url="", signer_pk="", anchor_address="", chain_id=2368)
    assert poster.live is False

    result = poster.post(_signed_update())  # type: ignore[arg-type]
    assert result.actor == _ACTOR
    assert result.score_e4 == 1234
    assert result.tx_hash == ""
    assert result.submitted is False
    assert poster.pending == [result]


def test_live_encoding_uses_postReputationUpdate_selector() -> None:
    """Confirms the ABI-driven encoder picks the right function without RPC."""
    poster = AnchorPoster(
        rpc_url="http://127.0.0.1:1",  # never dialled
        signer_pk=_PK,
        anchor_address=_ANCHOR,
        chain_id=2368,
    )
    poster._ensure_live()
    assert poster._contract is not None

    signed = _signed_update()
    u = signed.update  # type: ignore[attr-defined]
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
        ),
        signed.signature,  # type: ignore[attr-defined]
    )
    data = fn._encode_transaction_data()
    # Compare against the on-the-fly selector — robust to ABI tweaks.
    assert data.startswith(_expected_selector())


def _expected_selector() -> str:
    sig = (
        "postReputationUpdate(address,uint8,"
        "(int256,uint256,uint256,uint256,uint256,uint256,uint8),bytes)"
    )
    return "0x" + keccak(sig.encode())[:4].hex()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
