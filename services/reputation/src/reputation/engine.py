"""Reputation Engine — Phase 2.

Fetches per-strategy state from Goldsky over a 90d window, slices into 7d /
30d / 90d windows, computes cohort Sharpe statistics per class, scores each
strategy via the full `Helios.md §8.2` formula, signs the update, and
optionally posts on-chain.

Per `docs/phase2-plan.md` WS2.A, the engine lands in **shadow mode** first:
typehash v2 (with `componentsHash`) is computed and exposed via `/v1/audit`,
but signing/anchoring stays on v1 until `REPUTATION_TYPEHASH_VERSION=2` is
flipped after WS3.A's contract upgrade.
"""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass
from typing import Protocol

import structlog

from reputation.anchor import AnchorPoster, PostedUpdate
from reputation.cohort import cohort_stats, neutral
from reputation.goldsky import AllocatorState, NavEvent, StrategyState, TradeEvent
from reputation.score import (
    AllocatorScoreInputs,
    AllocatorScoreOutputs,
    CohortContext,
    ScoreInputs,
    ScoreOutputs,
    WindowSharpe,
    annualized_sharpe_from_nav,
    compute_allocator_score,
    compute_score,
)
from reputation.signer import (
    ActorType,
    ReputationSigner,
    ReputationUpdate,
    SignedUpdate,
)
from reputation.windows import slice_windows

_log = structlog.get_logger(__name__)
_NINETY_DAYS_SEC = 90 * 24 * 60 * 60
# WS5.A: 30d window for allocator retention + breach-discipline. Strategy
# scoring uses 90d (Sharpe windows) but allocator inputs are aggregated
# over a tighter window so churn + breach response track recent behavior.
_THIRTY_DAYS_SEC = 30 * 24 * 60 * 60


class _GoldskyProto(Protocol):
    async def fetch_strategy_states(self, since_unix: int) -> list[StrategyState]: ...

    async def aclose(self) -> None: ...


@dataclass(frozen=True, slots=True)
class EngineUpdate:
    state: StrategyState
    inputs: ScoreInputs
    outputs: ScoreOutputs
    signed: SignedUpdate
    cohort: CohortContext
    posted: PostedUpdate | None = None


@dataclass(frozen=True, slots=True)
class AllocatorEngineUpdate:
    """Parallel to `EngineUpdate` but for allocator (`ActorType.ALLOCATOR`)
    scoring. The signed payload uses the same `ReputationUpdate` typehash
    (v1/v2) as strategies — the contract distinguishes by `actorType`."""

    state: AllocatorState
    inputs: AllocatorScoreInputs
    outputs: AllocatorScoreOutputs
    signed: SignedUpdate
    posted: PostedUpdate | None = None


def _dedup_key(u: ReputationUpdate) -> tuple[object, ...]:
    """Semantic identity of the on-chain `ReputationData` payload, keyed by
    everything the contract stores **except `lastUpdateBlock`**.

    `lastUpdateBlock` is reset to `now_unix` every tick (see
    `_compute_update` / `_compute_allocator_update`), so it must be excluded
    or the payload would never be byte-identical and dedup could never fire.
    Excluding it is safe: the only on-chain consumer of `lastUpdateBlock` is
    `ReputationAnchor`'s monotonic replay guard
    (`data.lastUpdateBlock <= prev.lastUpdateBlock` reverts `StaleUpdate()`),
    and since we still set it to `now_unix` on every *actual* post, a post
    after a long skip gap always carries a strictly larger value and never
    trips that guard.

    `components_hash` is included as a safe superset: v1 does not store it
    on-chain, but it is derived from the rounded e4 component tuple
    (`score.py`), so sub-quantum window-slide drift yields an identical key
    while any on-chain-visible component move flips it. Version-agnostic —
    derived from `ReputationUpdate` fields, never the packed calldata.
    """
    return (
        u.actor.lower(),
        int(u.actor_type),
        int(u.current_score),
        int(u.total_attested_trades),
        int(u.total_realized_pnl),
        int(u.max_drawdown_bps),
        int(u.proof_validity_rate_bps),
        bytes(u.components_hash or b"").rjust(32, b"\x00"),
    )


class ReputationEngine:
    def __init__(
        self,
        goldsky: _GoldskyProto,
        signer: ReputationSigner,
        poll_interval_sec: int = 60,
        anchor: AnchorPoster | None = None,
        force_repost_sec: int = 0,
    ) -> None:
        self._goldsky = goldsky
        self._signer = signer
        self._anchor = anchor
        self._interval = max(5, poll_interval_sec)
        # Gas optimization: skip the on-chain `postReputationUpdate` tx when
        # an actor's payload is semantically unchanged since the last
        # SUCCESSFULLY-SUBMITTED post. There is no on-chain freshness gate on
        # reputation (registries are write-only delta sinks; contrast the
        # oracle's real 180s AllocatorVault gate), so skipping is zero-impact.
        # `force_repost_sec > 0` re-posts an unchanged payload at least that
        # often purely as a cosmetic /audit + subgraph freshness heartbeat.
        self._force_repost_sec = max(0, force_repost_sec)
        # (actor.lower(), actor_type_int) -> (dedup_key, armed_at_unix).
        # Armed ONLY on a genuinely submitted post (mirrors the oracle anchor
        # `rec.submitted` discipline). In-memory only: a restart empties it,
        # so each actor re-posts exactly once then dedup resumes — harmless
        # and desirable; deliberately NOT seeded from chain.
        self._last_submitted: dict[tuple[str, int], tuple[tuple[object, ...], int]] = {}
        self._skip_unchanged_count = 0
        self._post_count = 0
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._latest: dict[str, EngineUpdate] = {}
        self._subscribers: set[asyncio.Queue[EngineUpdate]] = set()
        # PR5 (phase2-review.md, perf list): per-strategy 90d rolling window
        # kept in memory across ticks. The engine queries Goldsky with
        # `since = max(now - 90d, min per-strategy hwm)` so a cold start
        # still pulls the full window but a warm tick only pulls the delta.
        # Each cached entry holds the last seen trade + nav timestamps so
        # we de-dup events (same timestamp may reappear on overlap).
        self._cache_trades: dict[str, list[TradeEvent]] = {}
        self._cache_navs: dict[str, list[NavEvent]] = {}
        self._cache_trade_hwm: dict[str, int] = {}
        self._cache_nav_hwm: dict[str, int] = {}
        # WS5.A: per-allocator latest update. Allocator state is
        # pre-aggregated upstream (in Goldsky), so no rolling window
        # cache is needed here — each tick refetches the full 30d slice.
        self._latest_allocators: dict[str, AllocatorEngineUpdate] = {}

    @property
    def latest(self) -> dict[str, EngineUpdate]:
        return dict(self._latest)

    @property
    def latest_allocators(self) -> dict[str, AllocatorEngineUpdate]:
        return dict(self._latest_allocators)

    @property
    def post_count(self) -> int:
        return self._post_count

    @property
    def skipped_unchanged_count(self) -> int:
        return self._skip_unchanged_count

    def _should_post(self, u: ReputationUpdate, now_unix: int) -> bool:
        """False ⇒ skip the on-chain tx because the last successfully
        submitted payload for this actor is semantically identical
        (excluding `lastUpdateBlock`) and the optional cosmetic
        force-repost interval has not elapsed."""
        prev = self._last_submitted.get((u.actor.lower(), int(u.actor_type)))
        if prev is None:
            return True  # never submitted (or first tick after restart)
        prev_key, armed_at = prev
        if _dedup_key(u) != prev_key:
            return True  # genuine on-chain-visible change
        # Payload unchanged: re-post only if the cosmetic force-repost
        # interval has elapsed (no on-chain consumer requires this).
        return self._force_repost_sec > 0 and now_unix - armed_at >= self._force_repost_sec

    def _arm_if_submitted(
        self, u: ReputationUpdate, posted: PostedUpdate | None, now_unix: int
    ) -> None:
        """Advance the cache ONLY on a genuinely submitted post. Dry-run
        (`posted is None`), registry-skip / RPC failure (`submitted` False)
        all leave the cache untouched so the next tick retries."""
        if posted is not None and posted.submitted:
            self._last_submitted[(u.actor.lower(), int(u.actor_type))] = (
                _dedup_key(u),
                now_unix,
            )

    async def _maybe_post(
        self, update: ReputationUpdate, signed: SignedUpdate, now_unix: int
    ) -> PostedUpdate | None:
        """Shared gate for the strategy + allocator post seams."""
        if self._anchor is None:
            return None
        if not self._should_post(update, now_unix):
            self._skip_unchanged_count += 1
            _log.info(
                "reputation.anchor.skip_unchanged",
                actor=update.actor,
                actor_type=int(update.actor_type),
                score_e4=update.current_score,
            )
            return None
        posted = await self._anchor.post_async(signed)
        self._arm_if_submitted(update, posted, now_unix)
        if posted.submitted:
            self._post_count += 1
        return posted

    def subscribe(self) -> asyncio.Queue[EngineUpdate]:
        q: asyncio.Queue[EngineUpdate] = asyncio.Queue(maxsize=128)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[EngineUpdate]) -> None:
        self._subscribers.discard(q)

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="reputation.engine")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None
        await self._goldsky.aclose()

    async def tick_once(self, now_unix: int | None = None) -> list[EngineUpdate]:
        ts = now_unix if now_unix is not None else int(time.time())
        cutoff = ts - _NINETY_DAYS_SEC
        # Pull only the delta since the laggard strategy's last seen event,
        # bounded below by the 90d cutoff. Cold start (no cache) falls back
        # to the full 90d, matching the previous behaviour.
        all_hwms = list(self._cache_trade_hwm.values()) + list(self._cache_nav_hwm.values())
        since = max(cutoff, min(all_hwms)) if all_hwms else cutoff
        try:
            states = await self._goldsky.fetch_strategy_states(since)
        except Exception as exc:
            _log.warning("reputation.goldsky.error", err=str(exc), exc_info=True)
            return []

        # If any strategy in the response has no cache entry yet, its
        # window came back clipped at `since` rather than `cutoff`
        # (Goldsky's `timestamp_gte` is a global filter on event
        # timestamps). Refetch from `cutoff` so backdated events for
        # newly-observed strategies are not silently dropped. The merge
        # path dedupes the redundant rows for already-cached strategies
        # via the per-strategy HWM filter.
        unseen = any(
            s.strategy_id not in self._cache_trade_hwm and s.strategy_id not in self._cache_nav_hwm
            for s in states
        )
        if unseen and since > cutoff:
            try:
                states = await self._goldsky.fetch_strategy_states(cutoff)
            except Exception as exc:
                _log.warning("reputation.goldsky.refetch_error", err=str(exc), exc_info=True)

        # Merge the incremental events into the rolling window and rebuild
        # the per-strategy state objects the rest of the pipeline expects.
        merged_states = [self._merge_state(s, cutoff) for s in states]

        # WS7.A: when last_rotation_epoch > 0, perf+age windows reset to
        # the rotation epoch (track-record breaks visibly across
        # rotations). Risk + proof use the full 90d window so a rotation
        # cannot wipe drawdown / proof history.
        #
        # The cohort context is built from the SAME post-rotation sharpes
        # that each strategy's score normalizes against. Otherwise a
        # rotated strategy's 7d sharpe would compare to a cohort median
        # computed from full-window sharpes, mixing pre/post-rotation
        # inputs across the comparison.
        effective_by_strategy = {s.strategy_id: _effective_window(s, ts) for s in merged_states}
        sharpes_by_strategy = {sid: ew.sharpes for sid, ew in effective_by_strategy.items()}
        cohort_by_class = _build_cohorts(merged_states, sharpes_by_strategy)
        max_stake_by_class = _max_stake_by_class(merged_states)

        updates: list[EngineUpdate] = []
        for s in merged_states:
            ew = effective_by_strategy[s.strategy_id]
            update = await self._compute_update(
                state=s,
                now_unix=ts,
                sharpes=ew.sharpes,
                age_trades_attested=ew.age_trades_attested,
                cohort=cohort_by_class[s.declared_class],
                max_stake_in_class_e18=max_stake_by_class.get(s.declared_class, 0),
            )
            self._latest[s.strategy_id] = update
            updates.append(update)
            await self._fanout(update)

        _log.info("reputation.tick", count=len(updates))
        return updates

    def _merge_state(self, fresh: StrategyState, cutoff: int) -> StrategyState:
        """Merge a Goldsky-returned state's trades + nav window into the
        engine cache, evict events older than the 90d cutoff, and return a
        StrategyState whose `trades_90d` / `nav_snapshots_90d` are the
        cached rolling window."""
        sid = fresh.strategy_id
        trade_hwm = self._cache_trade_hwm.get(sid, 0)
        nav_hwm = self._cache_nav_hwm.get(sid, 0)

        cached_trades = [t for t in self._cache_trades.get(sid, []) if t.timestamp >= cutoff]
        cached_navs = [n for n in self._cache_navs.get(sid, []) if n.timestamp >= cutoff]

        # Strict `>` so a timestamp at the boundary (already in cache) is
        # not double-counted. Goldsky's `timestamp_gte: $since` uses the
        # global minimum — every strategy at-or-past its own HWM is just
        # an overlap window, not new data.
        new_trades = [t for t in fresh.trades_90d if t.timestamp > trade_hwm]
        new_navs = [n for n in fresh.nav_snapshots_90d if n.timestamp > nav_hwm]

        merged_trades = cached_trades + new_trades
        merged_navs = cached_navs + new_navs

        if new_trades:
            trade_hwm = max(trade_hwm, *(t.timestamp for t in new_trades))
        if new_navs:
            nav_hwm = max(nav_hwm, *(n.timestamp for n in new_navs))

        self._cache_trades[sid] = merged_trades
        self._cache_navs[sid] = merged_navs
        self._cache_trade_hwm[sid] = trade_hwm
        self._cache_nav_hwm[sid] = nav_hwm

        return StrategyState(
            strategy_id=fresh.strategy_id,
            declared_class=fresh.declared_class,
            stake_e18=fresh.stake_e18,
            trades_attested=fresh.trades_attested,
            capital_deployed_e18=fresh.capital_deployed_e18,
            trades_90d=merged_trades,
            nav_snapshots_90d=merged_navs,
            last_rotation_epoch=fresh.last_rotation_epoch,
        )

    async def tick_allocators_once(
        self, now_unix: int | None = None
    ) -> list[AllocatorEngineUpdate]:
        """WS5.A: pull pre-aggregated 30d allocator state from Goldsky,
        compute the four-component allocator score, sign + post."""
        ts = now_unix if now_unix is not None else int(time.time())
        window_start = ts - _THIRTY_DAYS_SEC
        # Defensive: pre-WS5.B Goldsky stubs (and the existing strategy
        # test stubs) don't implement `fetch_allocator_states`. The
        # allocator branch silently no-ops in that case rather than
        # breaking the strategy tick that drives the same `_run` loop.
        fetcher = getattr(self._goldsky, "fetch_allocator_states", None)
        if fetcher is None:
            return []
        try:
            states = await fetcher(window_start)
        except Exception as exc:
            _log.warning("reputation.goldsky.allocator.error", err=str(exc), exc_info=True)
            return []

        updates: list[AllocatorEngineUpdate] = []
        for s in states:
            update = await self._compute_allocator_update(state=s, now_unix=ts)
            self._latest_allocators[s.allocator_id] = update
            updates.append(update)

        _log.info("reputation.tick.allocators", count=len(updates))
        return updates

    async def _compute_allocator_update(
        self, state: AllocatorState, now_unix: int
    ) -> AllocatorEngineUpdate:
        inputs = AllocatorScoreInputs(
            aggregate_pnl_above_hwm_e18=state.aggregate_pnl_above_hwm_e18,
            aggregate_capital_e18=state.aggregate_capital_e18,
            breach_total_count=state.breach_total_count,
            breach_response_count=state.breach_response_count,
            users_at_window_start=state.users_at_window_start,
            users_at_window_end=state.users_at_window_end,
            stake_e18=state.stake_e18,
            max_stake_in_class_e18=state.max_stake_in_class_e18,
        )
        outputs = compute_allocator_score(inputs)

        # `ReputationData` fields are strategy-shaped; for allocators we
        # repurpose what makes sense and zero the rest. The full
        # breakdown lives in `componentsHash` which the on-chain anchor
        # records verbatim regardless of actor type.
        update = ReputationUpdate(
            actor=state.allocator_id,
            actor_type=ActorType.ALLOCATOR,
            current_score=outputs.score_e4,
            last_update_block=now_unix,
            total_attested_trades=0,
            total_realized_pnl=max(0, state.aggregate_pnl_above_hwm_e18),
            max_drawdown_bps=0,
            proof_validity_rate_bps=0,
            components_hash=outputs.components_hash,
        )
        signed = self._signer.sign_update(update)
        posted = await self._maybe_post(update, signed, now_unix)
        return AllocatorEngineUpdate(
            state=state,
            inputs=inputs,
            outputs=outputs,
            signed=signed,
            posted=posted,
        )

    async def _run(self) -> None:
        while not self._stop.is_set():
            await self.tick_once()
            await self.tick_allocators_once()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
            except TimeoutError:
                continue

    async def _compute_update(
        self,
        state: StrategyState,
        now_unix: int,
        sharpes: WindowSharpe,
        age_trades_attested: int,
        cohort: CohortContext,
        max_stake_in_class_e18: int,
    ) -> EngineUpdate:
        windowed_trades = slice_windows(state.trades_90d, now_unix)
        # Subgraph only emits Trade events when the proof verifies on-chain;
        # failed-proof events aren't observable. Until the prover service
        # publishes attempted-but-rejected proofs (post-Phase-2), valid ==
        # attempts and the ratio is binary 0 / 1 by construction.
        valid_proofs = sum(1 for t in windowed_trades.last_30d if t.proof_valid)
        attempts = len(windowed_trades.last_30d)
        max_dd_bps_90d = _max_drawdown_bps(state.nav_snapshots_90d)
        realized_pnl_30d_e18 = _nav_delta(slice_windows(state.nav_snapshots_90d, now_unix).last_30d)

        # WS7.A post-rotation slicing is done once in `tick_once` via
        # `_effective_window` so cohort + per-strategy sharpes use the
        # same input. The score's age component picks up the
        # post-rotation trade count via the precomputed
        # `age_trades_attested` argument.

        inputs = ScoreInputs(
            sharpes=sharpes,
            max_drawdown_bps_90d=max_dd_bps_90d,
            valid_proofs=valid_proofs,
            total_proof_attempts=attempts,
            stake_e18=state.stake_e18,
            max_stake_in_class_e18=max_stake_in_class_e18,
            trades_attested=age_trades_attested,
        )
        outputs = compute_score(inputs, cohort)

        update = ReputationUpdate(
            actor=state.strategy_id,
            actor_type=ActorType.STRATEGY,
            current_score=outputs.score_e4,
            last_update_block=now_unix,
            total_attested_trades=state.trades_attested,
            total_realized_pnl=max(0, realized_pnl_30d_e18),
            max_drawdown_bps=max_dd_bps_90d,
            proof_validity_rate_bps=round(outputs.components.proof * 10_000),
            components_hash=outputs.components_hash,
        )
        signed = self._signer.sign_update(update)
        # Off the event loop: `wait_for_transaction_receipt(timeout=30)`
        # would otherwise stall every other strategy's score push + the
        # WS subscriber fanout for up to 30s per receipt. `_maybe_post`
        # also skips the tx entirely when the payload is unchanged.
        posted = await self._maybe_post(update, signed, now_unix)
        return EngineUpdate(
            state=state,
            inputs=inputs,
            outputs=outputs,
            signed=signed,
            cohort=cohort,
            posted=posted,
        )

    async def _fanout(self, update: EngineUpdate) -> None:
        dead: list[asyncio.Queue[EngineUpdate]] = []
        for q in self._subscribers:
            try:
                q.put_nowait(update)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self._subscribers.discard(q)


@dataclass(frozen=True, slots=True)
class _EffectiveWindow:
    """Per-strategy state slice used for the rep tick. Encapsulates the
    WS7.A post-rotation logic so cohort + per-strategy normalization see
    the same input."""

    sharpes: WindowSharpe
    age_trades_attested: int


def _effective_window(state: StrategyState, now_unix: int) -> _EffectiveWindow:
    """Return the (sharpes, age-trade-count) pair the rep tick should
    feed into the cohort builder and `_compute_update`.

    When `last_rotation_epoch > 0`, the perf+age inputs reset to the
    post-rotation slice — strict `>` so events at the rotation
    timestamp count as pre-rotation. Risk + proof keep the full 90d
    window, handled by `_compute_update`.
    """
    rotation_epoch = state.last_rotation_epoch
    if rotation_epoch > 0:
        post_navs = [n for n in state.nav_snapshots_90d if n.timestamp > rotation_epoch]
        post_trades = [t for t in state.trades_90d if t.timestamp > rotation_epoch]
        return _EffectiveWindow(
            sharpes=_windowed_sharpes_from_navs(post_navs, now_unix),
            age_trades_attested=len(post_trades),
        )
    return _EffectiveWindow(
        sharpes=_windowed_sharpes(state, now_unix),
        age_trades_attested=state.trades_attested,
    )


def _windowed_sharpes(state: StrategyState, now_unix: int) -> WindowSharpe:
    return _windowed_sharpes_from_navs(state.nav_snapshots_90d, now_unix)


def _windowed_sharpes_from_navs(navs: list[NavEvent], now_unix: int) -> WindowSharpe:
    w = slice_windows(navs, now_unix)
    return WindowSharpe(
        sharpe_7d=annualized_sharpe_from_nav(_to_pairs(w.last_7d)),
        sharpe_30d=annualized_sharpe_from_nav(_to_pairs(w.last_30d)),
        sharpe_90d=annualized_sharpe_from_nav(_to_pairs(w.last_90d)),
    )


def _to_pairs(events: list[NavEvent]) -> list[tuple[int, int]]:
    return [(e.timestamp, e.total_nav_e18) for e in events]


def _build_cohorts(
    states: list[StrategyState],
    sharpes_by_strategy: dict[str, WindowSharpe],
) -> dict[str, CohortContext]:
    by_class: dict[str, list[WindowSharpe]] = {}
    for s in states:
        by_class.setdefault(s.declared_class, []).append(sharpes_by_strategy[s.strategy_id])

    contexts: dict[str, CohortContext] = {}
    for cls, group in by_class.items():
        contexts[cls] = CohortContext(
            win_7d=cohort_stats([g.sharpe_7d for g in group]),
            win_30d=cohort_stats([g.sharpe_30d for g in group]),
            win_90d=cohort_stats([g.sharpe_90d for g in group]),
        )
    return contexts


def _max_stake_by_class(states: list[StrategyState]) -> dict[str, int]:
    out: dict[str, int] = {}
    for s in states:
        cur = out.get(s.declared_class, 0)
        if s.stake_e18 > cur:
            out[s.declared_class] = s.stake_e18
    return out


def _max_drawdown_bps(snapshots: list[NavEvent]) -> int:
    """Peak-to-trough drawdown over the snapshot window, returned in bps.

    Iterates ascending; tracks running peak; at each step records the dd_bps
    and keeps the max. Returns 0 when the window is empty or has no decline.

    Phase-3 review MEDIUM: cache merges currently preserve subgraph order,
    but a future event-source switch (Goldsky → on-chain index, replay
    log, etc.) could deliver out-of-order snapshots. A defensive
    `sorted()` keeps the peak/trough math correct regardless of source.
    The cost is O(n log n) over a 90-day window — bounded and tiny.
    """
    if not snapshots:
        return 0
    snapshots = sorted(snapshots, key=lambda ev: ev.timestamp)
    peak = 0
    max_dd_bps = 0
    for ev in snapshots:
        nav = ev.total_nav_e18
        if nav > peak:
            peak = nav
            continue
        if peak <= 0:
            continue
        dd_bps = math.floor((peak - nav) * 10_000 / peak)
        max_dd_bps = max(max_dd_bps, dd_bps)
    return max_dd_bps


def _nav_delta(snapshots: list[NavEvent]) -> int:
    if len(snapshots) < 2:
        return 0
    return snapshots[-1].total_nav_e18 - snapshots[0].total_nav_e18


# Dependency-injection helper for tests that pre-build cohorts.
def neutral_cohort() -> CohortContext:
    return CohortContext(win_7d=neutral(), win_30d=neutral(), win_90d=neutral())


__all__ = [
    "AllocatorEngineUpdate",
    "EngineUpdate",
    "ReputationEngine",
    "neutral_cohort",
]
