"""Gas optimization: skip the on-chain post when the reputation payload is
semantically unchanged since the last SUCCESSFULLY-SUBMITTED post.

There is no on-chain freshness gate on reputation (registries are write-only
delta sinks; the only contract guard is `ReputationAnchor`'s monotonic
`lastUpdateBlock` replay check, which `now_unix` keeps satisfying). So
skipping an unchanged payload is provably indistinguishable on-chain. The
cache arms ONLY on `PostedUpdate.submitted is True`, mirroring the oracle
anchor's `rec.submitted` discipline.
"""

from __future__ import annotations

import pytest
from reputation.anchor import PostedUpdate
from reputation.engine import ReputationEngine
from reputation.goldsky import AllocatorState, NavEvent, StrategyState, TradeEvent
from reputation.signer import ReputationSigner
from reputation.windows import DAY_SEC

_NOW = 1_700_000_000
_CLASS = "0x" + "11" * 32


class _StubGoldsky:
    def __init__(self, states: list[StrategyState]) -> None:
        self._states = states

    def set(self, states: list[StrategyState]) -> None:
        self._states = states

    async def fetch_strategy_states(self, since_unix: int) -> list[StrategyState]:
        del since_unix
        return list(self._states)

    async def fetch_allocator_states(self, window_start_unix: int) -> list[AllocatorState]:
        del window_start_unix
        return []

    async def aclose(self) -> None:  # pragma: no cover
        return None


class _StubAllocGoldsky:
    def __init__(self, allocators: list[AllocatorState]) -> None:
        self._allocators = allocators

    async def fetch_strategy_states(self, since_unix: int) -> list[object]:
        del since_unix
        return []

    async def fetch_allocator_states(self, window_start_unix: int) -> list[AllocatorState]:
        del window_start_unix
        return list(self._allocators)

    async def aclose(self) -> None:  # pragma: no cover
        return None


class _SpyAnchor:
    """Records every `post_async` call; returns a configurable outcome."""

    def __init__(self, *, submitted: bool = True, error: str = "") -> None:
        self.calls: list[object] = []
        self._submitted = submitted
        self._error = error

    async def post_async(self, signed: object) -> PostedUpdate:
        self.calls.append(signed)
        update = signed.update  # type: ignore[attr-defined]
        return PostedUpdate(
            actor=update.actor,
            score_e4=update.current_score,
            tx_hash="0x" + "ab" * 32 if self._submitted else "",
            submitted=self._submitted,
            error=self._error,
        )


@pytest.fixture()
def signer() -> ReputationSigner:
    return ReputationSigner("0x" + "22" * 32, chain_id=2368, anchor_address="0x" + "ab" * 20)


@pytest.fixture()
def signer_v2() -> ReputationSigner:
    return ReputationSigner(
        "0x" + "22" * 32, chain_id=2368, anchor_address="0x" + "ab" * 20, typehash_version="2"
    )


def _trending_navs(start_e18: int, daily_drift: float, days: int) -> list[NavEvent]:
    return [
        NavEvent(
            timestamp=_NOW - (days - 1 - d) * DAY_SEC,
            total_nav_e18=int(start_e18 * (1 + daily_drift) ** d),
        )
        for d in range(days)
    ]


def _state(
    strategy_id: str,
    *,
    trades_attested: int = 100,
    nav_drift: float = 0.001,
    nav_days: int = 30,
) -> StrategyState:
    return StrategyState(
        strategy_id=strategy_id,
        declared_class=_CLASS,
        stake_e18=5_000 * 10**18,
        trades_attested=trades_attested,
        capital_deployed_e18=10**18,
        trades_90d=[
            TradeEvent(timestamp=_NOW - d * DAY_SEC, proof_valid=True, amount_in_e18=10**18)
            for d in range(0, nav_days, 3)
        ],
        nav_snapshots_90d=_trending_navs(10**18, nav_drift, nav_days),
    )


def _alloc(allocator_id: str, *, pnl_e18: int = 0) -> AllocatorState:
    return AllocatorState(
        allocator_id=allocator_id,
        declared_class=_CLASS,
        stake_e18=5_000 * 10**18,
        max_stake_in_class_e18=10_000 * 10**18,
        aggregate_pnl_above_hwm_e18=pnl_e18,
        aggregate_capital_e18=100 * 10**18,
        breach_total_count=0,
        breach_response_count=0,
        users_at_window_start=3,
        users_at_window_end=3,
    )


def _engine(
    goldsky: object, signer: ReputationSigner, anchor: object, **kw: int
) -> ReputationEngine:
    return ReputationEngine(goldsky, signer, poll_interval_sec=60, anchor=anchor, **kw)  # type: ignore[arg-type]


# (a) unchanged payload across two ticks → exactly one post, one skip.
@pytest.mark.asyncio
async def test_unchanged_payload_posts_once_then_skips(signer: ReputationSigner) -> None:
    spy = _SpyAnchor(submitted=True)
    eng = _engine(_StubGoldsky([_state("0x" + "cd" * 20)]), signer, spy)
    await eng.tick_once(now_unix=_NOW)
    await eng.tick_once(now_unix=_NOW + 60)
    assert len(spy.calls) == 1
    assert eng.post_count == 1
    assert eng.skipped_unchanged_count == 1


# (b) a genuine score/components change → posts again.
@pytest.mark.asyncio
async def test_changed_payload_reposts(signer: ReputationSigner) -> None:
    spy = _SpyAnchor(submitted=True)
    stub = _StubGoldsky([_state("0x" + "cd" * 20, trades_attested=100)])
    eng = _engine(stub, signer, spy)
    await eng.tick_once(now_unix=_NOW)
    # total_attested_trades is part of the on-chain payload + dedup key.
    stub.set([_state("0x" + "cd" * 20, trades_attested=900)])
    await eng.tick_once(now_unix=_NOW + 60)
    assert len(spy.calls) == 2
    assert eng.post_count == 2
    assert eng.skipped_unchanged_count == 0


# (c) failed / registry-skipped submit must NOT arm the cache.
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", ["boom: rpc reverted", "skipped: actor not in active registry set"]
)
async def test_unsubmitted_does_not_arm(signer: ReputationSigner, error: str) -> None:
    spy = _SpyAnchor(submitted=False, error=error)
    eng = _engine(_StubGoldsky([_state("0x" + "cd" * 20)]), signer, spy)
    await eng.tick_once(now_unix=_NOW)
    await eng.tick_once(now_unix=_NOW + 60)
    assert len(spy.calls) == 2  # every tick retries — cache never armed
    assert eng.post_count == 0
    assert eng.skipped_unchanged_count == 0


# (d) force_repost_sec re-posts an unchanged payload after the interval.
@pytest.mark.asyncio
async def test_force_repost_interval(signer: ReputationSigner) -> None:
    spy = _SpyAnchor(submitted=True)
    eng = _engine(_StubGoldsky([_state("0x" + "cd" * 20)]), signer, spy, force_repost_sec=120)
    await eng.tick_once(now_unix=_NOW)  # post, arm @ _NOW
    await eng.tick_once(now_unix=_NOW + 60)  # 60 < 120 → skip
    await eng.tick_once(now_unix=_NOW + 200)  # 200 >= 120 → forced re-post, re-arm
    await eng.tick_once(now_unix=_NOW + 260)  # 60 since re-arm → skip
    assert len(spy.calls) == 2
    assert eng.post_count == 2
    assert eng.skipped_unchanged_count == 2


@pytest.mark.asyncio
async def test_force_repost_zero_never_forces(signer: ReputationSigner) -> None:
    spy = _SpyAnchor(submitted=True)
    eng = _engine(_StubGoldsky([_state("0x" + "cd" * 20)]), signer, spy, force_repost_sec=0)
    await eng.tick_once(now_unix=_NOW)
    # Sub-day gap: rolling windows don't slide past a daily-spaced point, so
    # the payload is unchanged and (force=0) it is never re-posted.
    await eng.tick_once(now_unix=_NOW + 200)
    assert len(spy.calls) == 1
    assert eng.skipped_unchanged_count == 1


# (e) dedup is version-invariant (derived from struct fields, not packed bytes).
@pytest.mark.asyncio
async def test_dedup_invariant_under_typehash_v2(signer_v2: ReputationSigner) -> None:
    spy = _SpyAnchor(submitted=True)
    eng = _engine(_StubGoldsky([_state("0x" + "cd" * 20)]), signer_v2, spy)
    await eng.tick_once(now_unix=_NOW)
    await eng.tick_once(now_unix=_NOW + 60)
    assert len(spy.calls) == 1
    assert eng.skipped_unchanged_count == 1


# (f) fresh engine (process restart) re-posts once then dedups.
@pytest.mark.asyncio
async def test_restart_reposts_once(signer: ReputationSigner) -> None:
    stub = _StubGoldsky([_state("0x" + "cd" * 20)])
    eng_a = _engine(stub, signer, _SpyAnchor(submitted=True))
    await eng_a.tick_once(now_unix=_NOW)
    await eng_a.tick_once(now_unix=_NOW + 60)
    spy_b = _SpyAnchor(submitted=True)
    eng_b = _engine(stub, signer, spy_b)  # empty in-memory cache
    await eng_b.tick_once(now_unix=_NOW + 120)
    await eng_b.tick_once(now_unix=_NOW + 180)
    assert len(spy_b.calls) == 1  # one re-post after restart, then dedup
    assert eng_b.skipped_unchanged_count == 1


# (g) allocator path dedups too, with no strategy/allocator key collision.
@pytest.mark.asyncio
async def test_allocator_path_dedups(signer: ReputationSigner) -> None:
    spy = _SpyAnchor(submitted=True)
    eng = _engine(_StubAllocGoldsky([_alloc("0x" + "aa" * 20)]), signer, spy)
    await eng.tick_allocators_once(now_unix=_NOW)
    await eng.tick_allocators_once(now_unix=_NOW + 60)
    assert len(spy.calls) == 1
    assert eng.post_count == 1
    assert eng.skipped_unchanged_count == 1


# (h) 3-strategy cohort: changing one re-posts only that actor; peers skip;
# no cross-actor cache-key collision.
@pytest.mark.asyncio
async def test_cohort_dedups_per_actor(signer: ReputationSigner) -> None:
    spy = _SpyAnchor(submitted=True)
    s_a, s_b, s_c = ("0x" + c * 20 for c in ("1a", "2b", "3c"))
    stub = _StubGoldsky(
        [
            _state(s_a, trades_attested=100, nav_drift=0.003),
            _state(s_b, trades_attested=200, nav_drift=0.001),
            _state(s_c, trades_attested=300, nav_drift=-0.001),
        ]
    )
    eng = _engine(stub, signer, spy)
    await eng.tick_once(now_unix=_NOW)
    assert len(spy.calls) == 3  # cold start: all three post
    # Move ONLY s_a's own payload (trades_attested ∈ dedup key + on-chain).
    # Tick at the SAME now_unix so the rolling windows don't slide — the
    # only changed input across the cohort is s_a's trade count, isolating
    # the per-actor dedup property from window-edge score drift.
    stub.set(
        [
            _state(s_a, trades_attested=950, nav_drift=0.003),
            _state(s_b, trades_attested=200, nav_drift=0.001),
            _state(s_c, trades_attested=300, nav_drift=-0.001),
        ]
    )
    await eng.tick_once(now_unix=_NOW)
    posted_actors = {c.update.actor for c in spy.calls[3:]}  # type: ignore[attr-defined]
    assert posted_actors == {s_a}  # only the changed actor re-posts
    assert eng.skipped_unchanged_count == 2  # the two unchanged peers
