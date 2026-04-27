"""Reputation Engine — pulls Goldsky strategy rollups, computes Phase 1 score,
posts signed updates to ReputationAnchor."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import structlog

from reputation.anchor import AnchorPoster, PostedUpdate
from reputation.goldsky import GoldskyClient, StrategyRollup
from reputation.score import ScoreInputs, ScoreOutputs, compute_phase1_score
from reputation.signer import ActorType, ReputationSigner, ReputationUpdate, SignedUpdate

_log = structlog.get_logger(__name__)
_THIRTY_DAYS_SEC = 30 * 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class EngineUpdate:
    rollup: StrategyRollup
    inputs: ScoreInputs
    outputs: ScoreOutputs
    signed: SignedUpdate
    posted: PostedUpdate | None = None


class ReputationEngine:
    def __init__(
        self,
        goldsky: GoldskyClient,
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
        """One pass over all strategies. Used by tests."""
        ts = now_unix if now_unix is not None else int(time.time())
        since = ts - _THIRTY_DAYS_SEC
        try:
            rollups = await self._goldsky.fetch_strategy_rollups(since)
        except Exception as exc:
            _log.warning("reputation.goldsky.error", err=str(exc))
            return []
        updates: list[EngineUpdate] = []
        for r in rollups:
            update = self._compute_update(r, ts)
            self._latest[r.strategy_id] = update
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

    def _compute_update(self, rollup: StrategyRollup, now_unix: int) -> EngineUpdate:
        # Phase 1: every emitted TradeAttested event implies on-chain
        # verification already passed, so the validity rate is 1.0 unless we
        # later track "rejected attempts" off-chain. Until then, default to
        # 10_000 bps (full credit).
        proof_validity_bps = 10_000 if rollup.total_attested_trades > 0 else 0
        inputs = ScoreInputs(
            realized_pnl_30d_e18=rollup.realized_pnl_30d_e18,
            notional_e18=rollup.capital_deployed_e18,
            proof_validity_rate_bps=proof_validity_bps,
        )
        outputs = compute_phase1_score(inputs)
        update = ReputationUpdate(
            actor=rollup.strategy_id,
            actor_type=ActorType.STRATEGY,
            current_score=outputs.score_e4,
            # Block monotonicity is enforced on-chain. Off-chain we don't have
            # a precise block; using `now_unix` as the source's monotonic
            # cursor lets the on-chain replay-protection accept consecutive
            # ticks regardless of underlying block production.
            last_update_block=now_unix,
            total_attested_trades=rollup.total_attested_trades,
            total_realized_pnl=max(0, rollup.realized_pnl_30d_e18),
            max_drawdown_bps=0,  # Phase 2 wires the drawdown calc.
            proof_validity_rate_bps=proof_validity_bps,
        )
        signed = self._signer.sign_update(update)
        posted = self._anchor.post(signed) if self._anchor is not None else None
        return EngineUpdate(
            rollup=rollup, inputs=inputs, outputs=outputs, signed=signed, posted=posted
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
