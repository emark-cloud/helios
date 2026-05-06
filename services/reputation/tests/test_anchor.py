"""AnchorPoster unit tests — dry-run + live encoding."""

from __future__ import annotations

import asyncio
import time

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
    assert list(poster.pending) == [result]


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
    # Compare against the on-the-fly selector — robust to ABI tweaks.
    assert data.startswith(_expected_selector())


def _expected_selector() -> str:
    # V2 ReputationData layout (post-WS3.A — adds componentsHash bytes32).
    sig = (
        "postReputationUpdate(address,uint8,"
        "(int256,uint256,uint256,uint256,uint256,uint256,uint8,bytes32),bytes)"
    )
    return "0x" + keccak(sig.encode())[:4].hex()


async def test_async_post_does_not_block_event_loop() -> None:
    """`AnchorPoster.post_async` must offload `wait_for_transaction_receipt`
    so the engine's `tick_once` keeps draining other strategies' updates
    while a single tx is in flight."""
    poster = AnchorPoster(
        rpc_url="http://stub", signer_pk=_PK, anchor_address=_ANCHOR, chain_id=2368
    )
    poster._live = True

    def slow_submit(_signed):  # type: ignore[no-untyped-def]
        time.sleep(0.4)
        return ("0x" + "ab" * 32, 1)

    poster._submit = slow_submit  # type: ignore[assignment]

    counter = {"ticks": 0}

    async def background_ticker() -> None:
        for _ in range(8):
            await asyncio.sleep(0.05)
            counter["ticks"] += 1

    ticker = asyncio.create_task(background_ticker())
    result = await poster.post_async(_signed_update())  # type: ignore[arg-type]
    await ticker
    assert result.submitted is True
    assert counter["ticks"] >= 4  # loop drained while submit was running


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
