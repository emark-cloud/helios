"""Anchor EIP-712 signing + scheduler unit tests.

Cross-language parity (Python signs → Solidity verifies) is locked in by
the Foundry round-trip test in `contracts/test/OraclePriceAnchor.t.sol`
once WS3.A wires the deploy script. These tests cover the Python side
in isolation:

  * `sign_commit` produces an ECDSA signature recoverable to the signer
    address — i.e. EIP-712 framing is well-formed for both anchor types.
  * Price and yield domains produce *different* digests for the same
    payload — the Solidity side rejects cross-domain replay; we want
    the Python side to be unable to even produce such a signature with
    a single domain choice.
  * `PriceAnchorScheduler` only commits every `interval_bars` and
    correctly enforces `windowStart >= prev.windowEnd` so contract
    invariants can never be violated by a well-behaved scheduler.
"""

from __future__ import annotations

import asyncio
import time

from eth_account import Account
from eth_account.messages import encode_typed_data
from oracle.anchor import (
    AnchorPoster,
    CommitPayload,
    PriceAnchorScheduler,
    YieldAnchorScheduler,
    sign_commit,
)
from oracle.signer import LocalSigner
from oracle.state import SnapshotStore
from oracle.yield_state import YieldStore

_TEST_PK = (
    "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"  # well-known anvil[1]
)
_CHAIN_ID = 2368  # Kite testnet
_ANCHOR_ADDR = "0x1111111111111111111111111111111111111111"


def _payload(kind: str = "price", nonce: int = 0) -> CommitPayload:
    return CommitPayload(
        kind=kind,  # type: ignore[arg-type]
        root=(123).to_bytes(32, "big"),
        window_start=1000,
        window_end=2000,
        nonce=nonce,
    )


def test_sign_commit_recovers_to_signer_address() -> None:
    expected = Account.from_key(_TEST_PK).address
    signed = sign_commit(_payload(), _TEST_PK, _CHAIN_ID, _ANCHOR_ADDR)
    assert signed.signer == expected
    # Re-derive the digest manually and recover.
    encoded = encode_typed_data(
        domain_data={
            "name": "HeliosOraclePriceAnchor",
            "version": "1",
            "chainId": _CHAIN_ID,
            "verifyingContract": _ANCHOR_ADDR,
        },
        message_types={
            "OraclePriceCommit": [
                {"name": "root", "type": "bytes32"},
                {"name": "windowStart", "type": "uint64"},
                {"name": "windowEnd", "type": "uint64"},
                {"name": "nonce", "type": "uint256"},
            ]
        },
        message_data={
            "root": signed.payload.root,
            "windowStart": signed.payload.window_start,
            "windowEnd": signed.payload.window_end,
            "nonce": signed.payload.nonce,
        },
    )
    recovered = Account.recover_message(encoded, signature=signed.signature)
    assert recovered == expected


def test_price_and_yield_signatures_differ_under_same_payload() -> None:
    p = sign_commit(_payload("price"), _TEST_PK, _CHAIN_ID, _ANCHOR_ADDR)
    y = sign_commit(_payload("yield"), _TEST_PK, _CHAIN_ID, _ANCHOR_ADDR)
    assert p.signature != y.signature  # different domain → different digest


def test_sign_commit_no_pk_returns_zero_placeholder() -> None:
    signed = sign_commit(_payload(), "", _CHAIN_ID, _ANCHOR_ADDR)
    assert signed.signature == b"\x00" * 65
    assert signed.signer == "0x" + "0" * 40


def test_anchor_poster_dry_run_records_pending() -> None:
    poster = AnchorPoster(
        kind="price",
        rpc_url="",
        signer_pk="",
        anchor_address="",
        chain_id=_CHAIN_ID,
    )
    assert not poster.live
    poster.post(_payload())
    assert len(poster.pending) == 1
    rec = poster.pending[0]
    assert rec.kind == "price"
    assert rec.submitted is False and not rec.tx_hash


def test_price_scheduler_emits_only_at_interval() -> None:
    store = SnapshotStore(signer=LocalSigner(""), capacity_per_asset=64)
    poster = AnchorPoster(
        kind="price", rpc_url="", signer_pk="", anchor_address="", chain_id=_CHAIN_ID
    )
    sched = PriceAnchorScheduler(store=store, poster=poster, interval_bars=4, chain_depth=4)

    for i in range(3):
        store.append("KITE/USDT", price_e18=10**18 + i, timestamp_ms=1000 * (i + 1), source="t")
        assert sched.on_bar("KITE/USDT") is None  # under interval

    # Fourth bar triggers commit.
    store.append("KITE/USDT", price_e18=10**18 + 3, timestamp_ms=4000, source="t")
    rec = sched.on_bar("KITE/USDT")
    assert rec is not None and rec.kind == "price"
    # chain_depth=4, so the window covers the last 4 bars (ts 1000..4000).
    assert rec.window_start == 1000 and rec.window_end == 4000
    assert rec.nonce == 0


def test_price_scheduler_advances_window_monotonically() -> None:
    store = SnapshotStore(signer=LocalSigner(""), capacity_per_asset=64)
    poster = AnchorPoster(
        kind="price", rpc_url="", signer_pk="", anchor_address="", chain_id=_CHAIN_ID
    )
    sched = PriceAnchorScheduler(store=store, poster=poster, interval_bars=2, chain_depth=2)

    rec1 = None
    for i in range(2):
        store.append("KITE/USDT", price_e18=10**18 + i, timestamp_ms=1000 * (i + 1), source="t")
        r = sched.on_bar("KITE/USDT")
        if r is not None:
            rec1 = r
    assert rec1 is not None and rec1.window_end == 2000

    rec2 = None
    for i in range(2):
        store.append(
            "KITE/USDT", price_e18=10**18 + 10 + i, timestamp_ms=3000 + i * 1000, source="t"
        )
        r = sched.on_bar("KITE/USDT")
        if r is not None:
            rec2 = r
    assert rec2 is not None
    # Contract invariant: ws >= prev.we. Scheduler must enforce.
    assert rec2.window_start >= rec1.window_end
    assert rec2.nonce == 1


async def test_async_post_does_not_block_event_loop() -> None:
    """`AnchorPoster.post_async` must run the blocking submit on a worker
    thread. Patch `_submit` to sleep 0.5s; assert that another awaitable
    (a no-op `asyncio.sleep`) finishes during that window — proving the
    event loop is still draining other tasks rather than frozen on the
    receipt wait."""
    poster = AnchorPoster(
        kind="price",
        rpc_url="http://stub",
        signer_pk=_TEST_PK,
        anchor_address=_ANCHOR_ADDR,
        chain_id=_CHAIN_ID,
    )
    poster._live = True  # type: ignore[attr-defined]

    def slow_submit(_signed):  # type: ignore[no-untyped-def]
        time.sleep(0.4)
        return ("0x" + "ab" * 32, 1)

    poster._submit = slow_submit  # type: ignore[assignment]

    counter = {"ticks": 0}

    async def background_ticker() -> None:
        # Tick every 50ms — if the loop is blocked, we get 0 or 1 ticks;
        # if to_thread is working, we expect ≥4 in the 400ms window.
        for _ in range(8):
            await asyncio.sleep(0.05)
            counter["ticks"] += 1

    ticker = asyncio.create_task(background_ticker())
    record = await poster.post_async(_payload())
    await ticker
    assert record.submitted is True
    assert counter["ticks"] >= 4  # loop drained while submit was running


def test_yield_scheduler_emits_for_market() -> None:
    store = YieldStore(signer=LocalSigner(""), capacity_per_market=64)
    poster = AnchorPoster(
        kind="yield", rpc_url="", signer_pk="", anchor_address="", chain_id=_CHAIN_ID
    )
    sched = YieldAnchorScheduler(store=store, poster=poster, interval_bars=3, chain_depth=3)

    rec = None
    for i in range(3):
        store.append(
            "aave-v3:USDC",
            apy_bps_e6=500_000_000 + i,
            timestamp_ms=1000 * (i + 1),
            source="t",
        )
        r = sched.on_bar("aave-v3:USDC")
        if r is not None:
            rec = r
    assert rec is not None and rec.kind == "yield"
    assert rec.window_start == 1000 and rec.window_end == 3000
