"""AnchorPoster unit tests — dry-run + live encoding."""

from __future__ import annotations

import asyncio
import contextlib
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


def test_v2_live_encoding_uses_v2_selector() -> None:
    """v2 poster picks the 8-field ABI (componentsHash) and emits the v2
    selector. Path used when pointed at the v2 anchor on a clean-slate chain."""
    poster = AnchorPoster(
        rpc_url="http://127.0.0.1:1",  # never dialled
        signer_pk=_PK,
        anchor_address=_ANCHOR,
        chain_id=2368,
        typehash_version="2",
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
    assert data.startswith(_v2_selector())


def test_v1_live_encoding_uses_v1_selector() -> None:
    """Default (typehash="1") poster MUST emit the 7-field v1 selector so
    the on-chain v1 anchor at 0x51c07adf… on Kite testnet accepts the call.
    Sending v2 calldata to a v1 anchor reverts with `('execution reverted',
    'no data')` because the v2 selector hits no handler — regression guard."""
    poster = AnchorPoster(
        rpc_url="http://127.0.0.1:1",  # never dialled
        signer_pk=_PK,
        anchor_address=_ANCHOR,
        chain_id=2368,
        # typehash_version="1" is the default — make it explicit for clarity
        typehash_version="1",
    )
    poster._ensure_live()
    assert poster._contract is not None

    signed = _signed_update()
    u = signed.update  # type: ignore[attr-defined]
    # 7-field tuple — no componentsHash slot.
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
    assert data.startswith(_v1_selector())
    # And the v1 selector must NOT collide with the v2 one — proves the
    # branch actually changed the calldata shape.
    assert _v1_selector() != _v2_selector()


def test_submit_payload_shape_branches_on_typehash() -> None:
    """`_submit` must build a 7-field tuple for v1 and 8-field for v2 —
    the engine signs typehash v1 by default; sending an 8-field tuple to
    the v1 anchor is what caused the production outage."""
    captured: dict[str, tuple] = {}

    class _StubFn:
        def build_transaction(self, _tx: dict) -> dict:  # pragma: no cover
            return {"data": "0x", "nonce": 0, "gas": 0, "gasPrice": 0}

    class _StubFns:
        def postReputationUpdate(self, actor, actor_type, data_tuple, sig):
            captured["v"] = data_tuple
            return _StubFn()

    class _StubContract:
        functions = _StubFns()

    for version, expected_len in (("1", 7), ("2", 8)):
        captured.clear()
        poster = AnchorPoster(
            rpc_url="http://stub",
            signer_pk=_PK,
            anchor_address=_ANCHOR,
            chain_id=2368,
            typehash_version=version,
        )
        # Bypass the real RPC wiring; the test cares about tuple shape only.
        poster._ensure_live()
        poster._contract = _StubContract()  # type: ignore[assignment]
        # Short-circuit before send_raw_transaction. The stub returns a
        # dict from build_transaction; downstream signing/sending will
        # error, but the test only cares that postReputationUpdate was
        # invoked with the right tuple shape — capture that and swallow.
        original_w3 = poster._w3
        with contextlib.suppress(Exception):
            poster._submit(_signed_update())  # type: ignore[arg-type]
        assert "v" in captured, f"v{version} did not call postReputationUpdate"
        assert len(captured["v"]) == expected_len, (
            f"v{version} sent {len(captured['v'])}-field tuple, want {expected_len}"
        )
        poster._w3 = original_w3


def _v1_selector() -> str:
    # V1 ReputationData layout — 7 fields (no componentsHash).
    sig = (
        "postReputationUpdate(address,uint8,"
        "(int256,uint256,uint256,uint256,uint256,uint256,uint8),bytes)"
    )
    return "0x" + keccak(sig.encode())[:4].hex()


def _v2_selector() -> str:
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


class _FakeRegistryCheck:
    """Stub `RegistryActiveCheck` for the post-time filter tests. Records
    every probe so the assertion can check the filter ran exactly once
    per submission attempt — no double-fire from a misplaced loop."""

    def __init__(self, active: bool) -> None:
        self._active = active
        self.probes: list[tuple[str, int]] = []

    def is_active(self, actor: str, actor_type: int) -> bool:
        self.probes.append((actor, actor_type))
        return self._active


def test_post_skips_when_registry_says_inactive() -> None:
    """Legacy pre-WS11 actors are still marked `active: true` in Goldsky's
    Strategy entity (V1 registry never emitted `StrategyDeactivated` for
    them) but SR-v3 doesn't know them. Without this filter the engine
    submits, wastes ~117k gas, and reverts `StrategyNotFound()`. The
    pre-flight short-circuits before `_submit` is reached."""
    poster = AnchorPoster(
        rpc_url="http://stub",
        signer_pk=_PK,
        anchor_address=_ANCHOR,
        chain_id=2368,
        registry_check=_FakeRegistryCheck(active=False),  # type: ignore[arg-type]
    )
    poster._live = True

    def boom_submit(_signed):  # type: ignore[no-untyped-def]
        raise AssertionError("_submit must not run for filtered actors")

    poster._submit = boom_submit  # type: ignore[assignment]
    result = poster.post(_signed_update())  # type: ignore[arg-type]
    assert result.submitted is False
    assert result.error.startswith("skipped:")
    assert result.tx_hash == ""
    # And it landed in `pending` so /v1/audit sees the skip alongside real posts.
    assert list(poster.pending) == [result]
    assert poster._registry_check.probes == [(_ACTOR, 0)]  # type: ignore[attr-defined]


def test_post_proceeds_when_registry_says_active() -> None:
    """Mirror of the skip test — when the registry says the actor IS
    active, `_submit` runs normally. Confirms the filter is gated, not
    blanket-skipping every submission."""
    captured: dict[str, object] = {}

    def stub_submit(signed):  # type: ignore[no-untyped-def]
        captured["actor"] = signed.update.actor
        return ("0x" + "cd" * 32, 42)

    poster = AnchorPoster(
        rpc_url="http://stub",
        signer_pk=_PK,
        anchor_address=_ANCHOR,
        chain_id=2368,
        registry_check=_FakeRegistryCheck(active=True),  # type: ignore[arg-type]
    )
    poster._live = True
    poster._submit = stub_submit  # type: ignore[assignment]

    result = poster.post(_signed_update())  # type: ignore[arg-type]
    assert result.submitted is True
    assert captured["actor"] == _ACTOR


def test_post_proceeds_when_registry_check_omitted() -> None:
    """Test-mode posture preserved: an AnchorPoster constructed without
    `registry_check` skips the pre-flight entirely (matches the e2e fake
    harnesses and existing unit tests). Regression guard against making
    the filter mandatory."""
    captured: dict[str, object] = {}

    def stub_submit(signed):  # type: ignore[no-untyped-def]
        captured["ran"] = True
        return ("0x" + "ef" * 32, 7)

    poster = AnchorPoster(
        rpc_url="http://stub",
        signer_pk=_PK,
        anchor_address=_ANCHOR,
        chain_id=2368,
    )
    poster._live = True
    poster._submit = stub_submit  # type: ignore[assignment]
    poster.post(_signed_update())  # type: ignore[arg-type]
    assert captured.get("ran") is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
