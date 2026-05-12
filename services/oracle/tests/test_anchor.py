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
    CommitRecord,
    MultiChainAnchorPoster,
    PriceAnchorScheduler,
    YieldAnchorScheduler,
    sign_commit,
)
from oracle.commit_mirror import CommitMirror
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


def test_price_scheduler_chains_globally_across_assets() -> None:
    """Regression: with N assets sharing one anchor, consecutive
    same-bar commits must chain through a *single global* monotonic
    counter (the contract's `_commits[last].windowEnd`), not per-asset
    state. Before the fix, asset B's `windowStart` was its own oldest
    snapshot ts, which sat before asset A's just-committed `windowEnd`,
    so A succeeded and B reverted `NonMonotonicWindow()` on chain — and
    the strategy proving against B's root saw `UnknownOracleRoot()`."""
    store = SnapshotStore(signer=LocalSigner(""), capacity_per_asset=64)
    poster = AnchorPoster(
        kind="price", rpc_url="", signer_pk="", anchor_address="", chain_id=_CHAIN_ID
    )
    sched = PriceAnchorScheduler(store=store, poster=poster, interval_bars=1, chain_depth=2)

    # Bar 1: all four assets carry the SAME newest_ts (real-world bar
    # boundary alignment) and overlapping oldest_ts windows.
    assets = ["KITE/USDT", "BTC/USDT", "ETH/USDT", "SOL/USDT"]
    for a in assets:
        store.append(a, price_e18=10**18, timestamp_ms=1000, source="t")
        store.append(a, price_e18=10**18, timestamp_ms=2000, source="t")

    records = []
    for a in assets:
        r = sched.on_bar(a)
        assert r is not None, f"{a} dropped a bar"
        records.append(r)

    # Each commit's windowStart must be >= the prior commit's windowEnd,
    # regardless of asset. Otherwise the contract reverts.
    for prev, curr in zip(records, records[1:], strict=False):
        assert curr.window_start >= prev.window_end, (
            f"non-monotonic across assets: {prev} → {curr}"
        )
    # And every window must be non-empty.
    for r in records:
        assert r.window_end > r.window_start
    # Nonces still strictly increase.
    assert [r.nonce for r in records] == [0, 1, 2, 3]


def test_live_post_uses_onchain_nonce_overriding_payload() -> None:
    """In live mode, the poster MUST read `nonce()` from the anchor
    instead of trusting the scheduler-tracked nonce. Without this,
    a process restart (off-chain `_nonce` reset to 0, on-chain still
    at N) would sign with stale nonce and revert with `InvalidSigner`
    forever."""
    poster = AnchorPoster(
        kind="price",
        rpc_url="http://stub",
        signer_pk=_TEST_PK,
        anchor_address=_ANCHOR_ADDR,
        chain_id=_CHAIN_ID,
    )
    poster._live = True  # type: ignore[attr-defined]

    poster._read_onchain_nonce = lambda: 42  # type: ignore[assignment]
    captured: list[int] = []

    def fake_submit(signed):  # type: ignore[no-untyped-def]
        captured.append(signed.payload.nonce)
        return ("0x" + "ab" * 32, 1)

    poster._submit = fake_submit  # type: ignore[assignment]

    # Off-chain says nonce=0 (e.g. fresh scheduler after restart); on-chain
    # is at 42. Signature must be over 42, not 0.
    record = poster.post(_payload(nonce=0))
    assert record.submitted is True
    assert record.nonce == 42
    assert captured == [42]


def test_live_post_resyncs_nonce_after_failed_submit() -> None:
    """If a submit fails (RPC error / tx revert), the next call must
    re-read on-chain nonce — which is unchanged because the failed tx
    didn't increment it. The scheduler's pre-incremented `_nonce`
    would otherwise drift permanently."""
    poster = AnchorPoster(
        kind="price",
        rpc_url="http://stub",
        signer_pk=_TEST_PK,
        anchor_address=_ANCHOR_ADDR,
        chain_id=_CHAIN_ID,
    )
    poster._live = True  # type: ignore[attr-defined]

    nonce_holder = {"value": 7}
    poster._read_onchain_nonce = lambda: nonce_holder["value"]  # type: ignore[assignment]

    calls = {"n": 0}

    def flaky_submit(signed):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("rpc connection reset")
        nonce_holder["value"] += 1  # on-chain increments only on success
        return ("0x" + "cd" * 32, calls["n"])

    poster._submit = flaky_submit  # type: ignore[assignment]

    # Scheduler-tracked nonce on the payload is irrelevant in live mode.
    fail = poster.post(_payload(nonce=99))
    assert fail.submitted is False and fail.nonce == 7
    ok = poster.post(_payload(nonce=99))
    assert ok.submitted is True
    assert ok.nonce == 7  # same on-chain nonce — failure didn't bump it


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
    poster._ensure_live = lambda: None  # type: ignore[assignment]
    poster._read_onchain_nonce = lambda: 0  # type: ignore[assignment]

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


def test_scheduler_resyncs_nonce_after_dry_run_to_live_transition() -> None:
    """After a dry-run rehearsal advances the scheduler's `_nonce`, a
    live submit reads on-chain `nonce()` and overrides the payload — so
    `record.nonce` reflects the on-chain value, not the scheduler's
    drifted counter. The scheduler must reconcile to that observed
    value so subsequent records (dry-run inspection or live retry)
    don't emit nonces the contract will never accept.

    Regression for `docs/phase-3-review.md` CRITICAL #2."""
    store = SnapshotStore(signer=LocalSigner(""), capacity_per_asset=64)
    poster = AnchorPoster(
        kind="price",
        rpc_url="http://stub",
        signer_pk=_TEST_PK,
        anchor_address=_ANCHOR_ADDR,
        chain_id=_CHAIN_ID,
    )
    sched = PriceAnchorScheduler(store=store, poster=poster, interval_bars=2, chain_depth=2)

    # Phase 1: dry-run (poster.live is False because rpc/signer/anchor are stub).
    # Force the dry-run path via a temporary stub `live` view: leave fields as
    # set, then drive two bars to advance the scheduler counter past 0.
    sched._nonce = 50  # simulate a long dry-run rehearsal

    # Flip to live mode. On-chain nonce starts at 7 (independent of the
    # scheduler's drifted 50).
    poster._ensure_live = lambda: None  # type: ignore[assignment]
    nonce_holder = {"value": 7}
    poster._read_onchain_nonce = lambda: nonce_holder["value"]  # type: ignore[assignment]

    def fake_submit(signed):  # type: ignore[no-untyped-def]
        nonce_holder["value"] += 1
        return ("0x" + "ab" * 32, 1)

    poster._submit = fake_submit  # type: ignore[assignment]
    # Make `live` True by populating the gating fields.
    object.__setattr__(poster, "rpc_url", "http://stub")
    object.__setattr__(poster, "signer_pk", _TEST_PK)
    object.__setattr__(poster, "anchor_address", _ANCHOR_ADDR)
    assert poster.live

    # Two bars at interval_bars=2 → one commit.
    rec = None
    for i in range(2):
        store.append("KITE/USDT", price_e18=10**18 + i, timestamp_ms=1000 * (i + 1), source="t")
        r = sched.on_bar("KITE/USDT")
        if r is not None:
            rec = r
    assert rec is not None
    assert rec.submitted is True
    assert rec.nonce == 7  # on-chain nonce, not scheduler's drifted 50.
    # Scheduler must now track the next-expected on-chain nonce (8).
    assert sched._nonce == 8


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


def test_multichain_post_dry_run_records_canonical_and_mirrors() -> None:
    canonical = AnchorPoster(
        kind="price", rpc_url="", signer_pk="", anchor_address="", chain_id=2368
    )
    base = AnchorPoster(kind="price", rpc_url="", signer_pk="", anchor_address="", chain_id=84_532)
    arb = AnchorPoster(kind="price", rpc_url="", signer_pk="", anchor_address="", chain_id=421_614)
    multi = MultiChainAnchorPoster(canonical=canonical, mirrors=[base, arb])

    rec = multi.post(_payload())
    assert rec.kind == "price"
    # Canonical record exposed via `pending`; mirrors tracked separately.
    assert len(canonical.pending) == 1
    assert len(multi.mirror_records) == 2  # one per mirror
    assert all(r.submitted is False for r in multi.mirror_records)


async def test_multichain_post_async_runs_chains_in_parallel() -> None:
    canonical = AnchorPoster(
        kind="price",
        rpc_url="http://k",
        signer_pk=_TEST_PK,
        anchor_address=_ANCHOR_ADDR,
        chain_id=2368,
    )
    base = AnchorPoster(
        kind="price",
        rpc_url="http://b",
        signer_pk=_TEST_PK,
        anchor_address=_ANCHOR_ADDR,
        chain_id=84_532,
    )
    for p in (canonical, base):
        p._ensure_live = lambda: None  # type: ignore[assignment]
        p._read_onchain_nonce = lambda: 0  # type: ignore[assignment, method-assign]

    def slow_submit(_signed):  # type: ignore[no-untyped-def]
        time.sleep(0.3)
        return ("0x" + "ab" * 32, 1)

    canonical._submit = slow_submit  # type: ignore[assignment]
    base._submit = slow_submit  # type: ignore[assignment]

    multi = MultiChainAnchorPoster(canonical=canonical, mirrors=[base])

    started = time.monotonic()
    rec = await multi.post_async(_payload())
    elapsed = time.monotonic() - started

    assert rec.submitted is True
    # Both submits sleep 0.3s — sequential would be ~0.6s; gather bounds it
    # under ~0.5s with comfortable headroom for thread-pool scheduling.
    assert elapsed < 0.5, f"chains ran sequentially (elapsed={elapsed:.3f}s)"
    assert len(multi.mirror_records) == 1
    assert multi.mirror_records[0].submitted is True


def test_multichain_post_isolates_mirror_failure_from_canonical() -> None:
    canonical = AnchorPoster(
        kind="price",
        rpc_url="http://k",
        signer_pk=_TEST_PK,
        anchor_address=_ANCHOR_ADDR,
        chain_id=2368,
    )
    bad_mirror = AnchorPoster(
        kind="price",
        rpc_url="http://b",
        signer_pk=_TEST_PK,
        anchor_address=_ANCHOR_ADDR,
        chain_id=84_532,
    )
    canonical._ensure_live = lambda: None  # type: ignore[assignment]
    canonical._read_onchain_nonce = lambda: 0  # type: ignore[assignment, method-assign]
    canonical._submit = lambda _s: ("0x" + "ee" * 32, 1)  # type: ignore[assignment]

    bad_mirror._ensure_live = lambda: None  # type: ignore[assignment]
    bad_mirror._read_onchain_nonce = lambda: 0  # type: ignore[assignment, method-assign]

    def boom(_s):  # type: ignore[no-untyped-def]
        raise RuntimeError("base sepolia rpc dead")

    bad_mirror._submit = boom  # type: ignore[assignment]

    multi = MultiChainAnchorPoster(canonical=canonical, mirrors=[bad_mirror])
    rec = multi.post(_payload())
    assert rec.submitted is True  # canonical succeeded
    assert len(multi.mirror_records) == 1
    mirror_rec: CommitRecord = multi.mirror_records[0]
    assert mirror_rec.submitted is False
    assert "base sepolia rpc dead" in mirror_rec.error


def test_commit_mirror_pins_window_to_each_successful_commit() -> None:
    """Regression for the on-chain `UnknownOracleRoot()` race: HTTP
    `/snapshots/recent` + `/snapshots/root` MUST serve from the mirror
    so strategy and anchor see the same window. Even with cadence=1,
    the live ring can advance between strategy fetch and submit; the
    mirror captures the exact `(snapshots, root, window_end)` triple
    the anchor verified, removing the race.
    """
    mirror = CommitMirror()
    store = SnapshotStore(signer=LocalSigner(""), capacity_per_asset=64)
    poster = AnchorPoster(
        kind="price", rpc_url="", signer_pk="", anchor_address="", chain_id=_CHAIN_ID
    )
    # Dry-run poster — `rec.submitted` is False, so the mirror MUST stay
    # empty even after on_bar() emits a record. Strategies should not
    # trust un-submitted roots.
    sched = PriceAnchorScheduler(
        store=store, poster=poster, interval_bars=2, chain_depth=2, mirror=mirror
    )
    for i in range(2):
        store.append("KITE/USDT", price_e18=10**18 + i, timestamp_ms=1000 * (i + 1), source="t")
        sched.on_bar("KITE/USDT")
    assert mirror.get("KITE/USDT") is None, "dry-run commits must not populate mirror"

    # Now switch the poster to "live-like" — return submitted=True from
    # _submit so the mirror records. We don't care about the real
    # signature; the scheduler treats `rec.submitted` as the trigger.
    poster.rpc_url = "http://stub"  # type: ignore[misc]
    poster.signer_pk = _TEST_PK  # type: ignore[misc]
    poster.anchor_address = _ANCHOR_ADDR  # type: ignore[misc]
    poster._ensure_live = lambda: None  # type: ignore[assignment]
    poster._read_onchain_nonce = lambda: 0  # type: ignore[assignment, method-assign]
    poster._submit = lambda _s: ("0x" + "aa" * 32, 1)  # type: ignore[assignment]

    # Two fresh bars → another commit. With live poster, the mirror
    # MUST now hold this window.
    for i in range(2):
        store.append(
            "KITE/USDT", price_e18=10**18 + 100 + i, timestamp_ms=3000 + i * 1000, source="t"
        )
        sched.on_bar("KITE/USDT")
    committed = mirror.get("KITE/USDT")
    assert committed is not None
    assert committed.window_end_ms == 4000  # newest timestamp in the committed window
    assert len(committed.snapshots) == 2  # chain_depth=2
    # snapshots are newest-first (mirrors SnapshotStore.recent ordering)
    assert committed.snapshots[0].timestamp_ms == 4000
    assert committed.snapshots[1].timestamp_ms == 3000
    # And the root in the mirror must equal the root the poseidon chain
    # produced — strategies will recompute and compare on-chain.
    expected_root = store.chain_root("KITE/USDT", 2)
    assert committed.root == expected_root


def test_commit_mirror_overwrites_previous_window() -> None:
    """The mirror only retains the most-recent committed window. After a
    new successful commit, strategies fetching from the mirror see the
    new window — older windows are intentionally discarded (the anchor
    only ever cares about the latest root for freshness checks)."""
    mirror = CommitMirror()
    store = SnapshotStore(signer=LocalSigner(""), capacity_per_asset=64)
    poster = AnchorPoster(
        kind="price",
        rpc_url="http://stub",
        signer_pk=_TEST_PK,
        anchor_address=_ANCHOR_ADDR,
        chain_id=_CHAIN_ID,
    )
    poster._ensure_live = lambda: None  # type: ignore[assignment]
    poster._read_onchain_nonce = lambda: 0  # type: ignore[assignment, method-assign]
    poster._submit = lambda _s: ("0x" + "bb" * 32, 1)  # type: ignore[assignment]
    sched = PriceAnchorScheduler(
        store=store, poster=poster, interval_bars=2, chain_depth=2, mirror=mirror
    )

    for i in range(2):
        store.append("KITE/USDT", price_e18=10**18 + i, timestamp_ms=1000 * (i + 1), source="t")
        sched.on_bar("KITE/USDT")
    first = mirror.get("KITE/USDT")
    assert first is not None and first.window_end_ms == 2000

    for i in range(2):
        store.append(
            "KITE/USDT", price_e18=10**18 + 100 + i, timestamp_ms=3000 + i * 1000, source="t"
        )
        sched.on_bar("KITE/USDT")
    second = mirror.get("KITE/USDT")
    assert second is not None and second.window_end_ms == 4000
    assert second.root != first.root
