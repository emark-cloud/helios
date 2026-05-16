"""Gas optimization: gate the per-bar RouterPriceMirror keeper behind a
GLOBAL liveness heartbeat, with an on-demand `force_refresh` that bypasses
the gate (ridden by the `/v1/anchor/commit` pre-trade hook).

The router price has NO on-chain freshness gate and its only consumer is
the in-flight `executeWithProof` swap, which now force-refreshes its own
asset at trade time — so suppressing idle per-bar posts is provably
indistinguishable on-chain. The clock arms ONLY on a genuinely submitted
tx (`record.submitted`), mirroring the oracle anchor's `_mark_committed`
and the reputation engine's `_arm_if_submitted` discipline.

Separate from `test_router_mirror.py` (that file is dry-run-only —
`live=False` can never set `submitted`, and the gate turns entirely on
`record.submitted`). Stubs Web3 out so submitted/failed outcomes are
deterministic, and injects a fake clock.
"""

from __future__ import annotations

import pytest
from oracle.router_mirror import PairSpec, RouterPriceMirror
from oracle.signer import LocalSigner
from oracle.state import SnapshotStore


class _FakeClock:
    """Monotonic-shaped injectable clock. `t` is seconds; the mirror
    multiplies by 1000 internally."""

    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


class _SpyMirror(RouterPriceMirror):
    """`RouterPriceMirror` with Web3 stubbed out: creds are non-empty so
    `live` is True, `_ensure_live` is a no-op, and `_set_price` records
    the call and either returns a fake hash or raises (per `_fail`).
    Mirrors the reputation `_SpyAnchor` pattern.

    `_SpyMirror` is a plain subclass (not re-decorated `@dataclass`), so
    these are ordinary class attributes — declared for the typechecker,
    set per-instance in `_spy()`."""

    _fail: bool = False
    _set_price_calls: list[tuple[str, str, int, int]]

    def _ensure_live(self) -> None:  # no Web3 construction
        return None

    def _set_price(self, token_in: str, token_out: str, num: int, denom: int) -> str:
        self._set_price_calls.append((token_in, token_out, num, denom))
        if self._fail:
            raise RuntimeError("stub: setPrice reverted")
        return "0x" + "ab" * 32


def _eth_pair() -> PairSpec:
    return PairSpec(
        oracle_asset="ETH/USDT",
        stable_address="0x" + "11" * 20,
        stable_decimals=6,
        asset_address="0x" + "22" * 20,
        asset_decimals=18,
    )


def _btc_pair() -> PairSpec:
    return PairSpec(
        oracle_asset="BTC/USDT",
        stable_address="0x" + "11" * 20,
        stable_decimals=6,
        asset_address="0x" + "44" * 20,
        asset_decimals=8,
    )


def _store(*pairs_prices: tuple[str, int]) -> SnapshotStore:
    store = SnapshotStore(signer=LocalSigner(""))
    for asset, price_e18 in pairs_prices:
        store.append(asset=asset, price_e18=price_e18, timestamp_ms=1_000, source="test")
    return store


def _spy(
    store: SnapshotStore,
    pairs: list[PairSpec],
    *,
    clock: _FakeClock,
    liveness_sec: int | None = None,
    fail: bool = False,
) -> _SpyMirror:
    m = _SpyMirror(
        store=store,
        rpc_url="http://stub",
        signer_pk="0x" + "11" * 32,
        router_address="0x" + "22" * 20,
        chain_id=2368,
        pairs=pairs,
        liveness_sec=liveness_sec,
        clock=clock,
    )
    # Per-instance spy state (RouterPriceMirror is a non-slots dataclass,
    # so instance attrs are free); typed via the class declarations above.
    m._fail = fail
    m._set_price_calls = []
    return m


# (1) legacy: liveness_sec=0 ⇒ unconditional per-bar (rollback path).
def test_legacy_gate_zero_posts_every_bar() -> None:
    pair = _eth_pair()
    clock = _FakeClock(0.0)
    m = _spy(_store((pair.oracle_asset, 3_000 * 10**18)), [pair], clock=clock, liveness_sec=0)
    for _ in range(5):
        rec = m.on_snapshot(pair.oracle_asset)
        assert rec is not None and rec.submitted
    assert m.posts == 5
    assert m.skipped == 0
    assert len(m._set_price_calls) == 10  # 2 directions per post


# (1b) legacy: liveness_sec=None behaves identically to 0.
def test_legacy_gate_none_posts_every_bar() -> None:
    pair = _eth_pair()
    clock = _FakeClock(0.0)
    m = _spy(_store((pair.oracle_asset, 3_000 * 10**18)), [pair], clock=clock, liveness_sec=None)
    for _ in range(3):
        assert m.on_snapshot(pair.oracle_asset) is not None
    assert m.posts == 3
    assert m.skipped == 0


# (2) gate suppresses within the window, then posts once past it.
def test_gate_suppresses_within_window_then_posts_after() -> None:
    pair = _eth_pair()
    clock = _FakeClock(0.0)
    m = _spy(_store((pair.oracle_asset, 3_000 * 10**18)), [pair], clock=clock, liveness_sec=1800)

    assert m.on_snapshot(pair.oracle_asset) is not None  # cold → posts, arm@0
    for t in (60.0, 120.0, 1799.0):
        clock.t = t
        assert m.on_snapshot(pair.oracle_asset) is None  # within window → skip
    clock.t = 1801.0
    assert m.on_snapshot(pair.oracle_asset) is not None  # past window → posts, re-arm

    assert m.posts == 2
    assert m.skipped == 3


# (3) force_refresh always posts even inside the window, and re-arms.
def test_force_refresh_always_posts_within_window() -> None:
    pair = _eth_pair()
    clock = _FakeClock(0.0)
    m = _spy(_store((pair.oracle_asset, 3_000 * 10**18)), [pair], clock=clock, liveness_sec=1800)

    assert m.on_snapshot(pair.oracle_asset) is not None  # posts, arm@0
    clock.t = 60.0
    forced = m.force_refresh(pair.oracle_asset)  # well inside window
    assert forced is not None and forced.submitted  # must post anyway
    clock.t = 120.0
    assert m.on_snapshot(pair.oracle_asset) is None  # 120-60=60 < 1800 → skip

    assert m.posts == 2  # 1 per-bar + 1 forced
    assert m.skipped == 1


@pytest.mark.asyncio
async def test_force_refresh_async_bypasses_gate() -> None:
    pair = _eth_pair()
    clock = _FakeClock(0.0)
    m = _spy(_store((pair.oracle_asset, 3_000 * 10**18)), [pair], clock=clock, liveness_sec=1800)
    assert await m.on_snapshot_async(pair.oracle_asset) is not None  # arm@0
    clock.t = 30.0
    forced = await m.force_refresh_async(pair.oracle_asset)
    assert forced is not None and forced.submitted
    assert m.posts == 2


# (4) a failed submit must NOT arm the clock — every bar retries.
def test_failed_submit_does_not_arm() -> None:
    pair = _eth_pair()
    clock = _FakeClock(0.0)
    m = _spy(
        _store((pair.oracle_asset, 3_000 * 10**18)),
        [pair],
        clock=clock,
        liveness_sec=1800,
        fail=True,
    )
    rec1 = m.on_snapshot(pair.oracle_asset)
    assert rec1 is not None and not rec1.submitted and rec1.error != ""
    # Next bar, well inside what *would* be the window: gate must still
    # allow (clock never armed) so the retry lands.
    clock.t = 1.0
    m._fail = False  # type: ignore[attr-defined]
    rec2 = m.on_snapshot(pair.oracle_asset)
    assert rec2 is not None and rec2.submitted
    assert m.posts == 1  # only the successful bar
    assert m.skipped == 0  # the failed attempt was retried, not suppressed


# (5) dry-run never arms (live=False returns before _mark) — a dry-run
# deploy keeps posting every bar, unaffected by the gate.
def test_dry_run_never_arms() -> None:
    pair = _eth_pair()
    clock = _FakeClock(0.0)
    dry = RouterPriceMirror(
        store=_store((pair.oracle_asset, 3_000 * 10**18)),
        rpc_url="",
        signer_pk="",
        router_address="",
        chain_id=2368,
        pairs=[pair],
        liveness_sec=1800,
        clock=clock,
    )
    assert dry.live is False
    r0 = dry.on_snapshot(pair.oracle_asset)
    clock.t = 1.0
    r1 = dry.on_snapshot(pair.oracle_asset)
    assert r0 is not None and not r0.submitted
    assert r1 is not None and not r1.submitted
    assert dry.posts == 0
    assert dry.skipped == 0
    assert len(dry.pending) == 2  # both bars recorded a dry-run entry


# (6) the core gas-win: an on-demand refresh satisfies the heartbeat so
# the next idle per-bar tick is correctly skipped.
def test_on_demand_then_per_bar_suppressed() -> None:
    pair = _eth_pair()
    clock = _FakeClock(10.0)
    m = _spy(_store((pair.oracle_asset, 3_000 * 10**18)), [pair], clock=clock, liveness_sec=1800)

    forced = m.force_refresh(pair.oracle_asset)  # trade-time refresh, arm@10
    assert forced is not None and forced.submitted
    clock.t = 70.0
    assert m.on_snapshot(pair.oracle_asset) is None  # 70-10=60 < 1800 → skip

    assert m.posts == 1
    assert m.skipped == 1


# (7) the gate is GLOBAL: a post for one asset suppresses a same-tick
# per-bar post for another (matches the oracle anchor's global clock).
def test_global_gate_across_assets() -> None:
    eth, btc = _eth_pair(), _btc_pair()
    clock = _FakeClock(0.0)
    store = _store((eth.oracle_asset, 3_000 * 10**18), (btc.oracle_asset, 50_000 * 10**18))
    m = _spy(store, [eth, btc], clock=clock, liveness_sec=1800)

    assert m.on_snapshot(eth.oracle_asset) is not None  # posts, arms global@0
    assert m.on_snapshot(btc.oracle_asset) is None  # same tick → suppressed

    assert m.posts == 1
    assert m.skipped == 1
