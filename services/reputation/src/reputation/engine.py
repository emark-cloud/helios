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
from reputation.goldsky import NavEvent, StrategyState
from reputation.score import (
    CohortContext,
    ScoreInputs,
    ScoreOutputs,
    WindowSharpe,
    annualized_sharpe_from_nav,
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


class ReputationEngine:
    def __init__(
        self,
        goldsky: _GoldskyProto,
        signer: ReputationSigner,
        poll_interval_sec: int = 60,
        anchor: AnchorPoster | None = None,
    ) -> None:
        self._goldsky = goldsky
        self._signer = signer
        self._anchor = anchor
        self._interval = max(5, poll_interval_sec)
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._latest: dict[str, EngineUpdate] = {}
        self._subscribers: set[asyncio.Queue[EngineUpdate]] = set()

    @property
    def latest(self) -> dict[str, EngineUpdate]:
        return dict(self._latest)

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
        since = ts - _NINETY_DAYS_SEC
        try:
            states = await self._goldsky.fetch_strategy_states(since)
        except Exception as exc:
            _log.warning("reputation.goldsky.error", err=str(exc), exc_info=True)
            return []

        # WS7.A: when last_rotation_epoch > 0, perf+age windows reset to
        # the rotation epoch (track-record breaks visibly across
        # rotations). Risk + proof use the full 90d window so a rotation
        # cannot wipe drawdown / proof history.
        sharpes_by_strategy = {s.strategy_id: _windowed_sharpes(s, ts) for s in states}
        cohort_by_class = _build_cohorts(states, sharpes_by_strategy)
        max_stake_by_class = _max_stake_by_class(states)

        updates: list[EngineUpdate] = []
        for s in states:
            update = self._compute_update(
                state=s,
                now_unix=ts,
                sharpes=sharpes_by_strategy[s.strategy_id],
                cohort=cohort_by_class[s.declared_class],
                max_stake_in_class_e18=max_stake_by_class.get(s.declared_class, 0),
            )
            self._latest[s.strategy_id] = update
            updates.append(update)
            await self._fanout(update)

        _log.info("reputation.tick", count=len(updates))
        return updates

    async def _run(self) -> None:
        while not self._stop.is_set():
            await self.tick_once()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
            except TimeoutError:
                continue

    def _compute_update(
        self,
        state: StrategyState,
        now_unix: int,
        sharpes: WindowSharpe,
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

        # WS7.A: post-rotation track record. When last_rotation_epoch > 0,
        # AgeScore counts only post-rotation attestations and PerformanceScore
        # uses Sharpes from post-rotation NAVs. The score input's
        # `trades_attested` becomes the post-rotation count — when zero,
        # `compute_score` takes the WS7.B cold-start path (stake-only floor)
        # which is the correct rendering of "track record reset".
        rotation_epoch = state.last_rotation_epoch
        if rotation_epoch > 0:
            # Strict `>` so events at the exact rotation timestamp count
            # as pre-rotation (the rotation tx is the boundary, not the
            # first post-rotation block). Matches "track record reset"
            # semantics: the strategy starts fresh from the next bar.
            post_navs = [n for n in state.nav_snapshots_90d if n.timestamp > rotation_epoch]
            post_trades = [t for t in state.trades_90d if t.timestamp > rotation_epoch]
            sharpes = _windowed_sharpes_from_navs(post_navs, now_unix)
            age_trades_attested = len(post_trades)
        else:
            age_trades_attested = state.trades_attested

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
        posted = self._anchor.post(signed) if self._anchor is not None else None
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
    """
    if not snapshots:
        return 0
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
    "EngineUpdate",
    "ReputationEngine",
    "neutral_cohort",
]
