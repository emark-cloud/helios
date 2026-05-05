"""Sentinel's decision loop.

Implements the six-step cycle from `Helios.md §11.2`:

  1. Discover & rank strategies (Goldsky directory + reputation)
  2. Compute target allocation (allocator's `allocate(...)`)
  3. Diff target against current allocations
  4. Drawdown check — highest priority, evicts before applying diffs
  5. Apply diffs (allocate / decrease / defund)
  6. Fee crystallization (NAV > HWM × (1 + FEE_THRESHOLD))

Cadence model: a single tick coordinator runs every
`drawdown_check_interval_sec` (60s default) and gates the heavier
operations behind their own intervals. This keeps the drawdown check
on its mandated cadence even when rank-update / rebalance /
fee-settlement are skipped.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable
from dataclasses import dataclass

import structlog
from helios_allocator.types import AllocationTarget, StrategyCandidate

from sentinel.allocator import SentinelAllocator, diff_allocations
from sentinel.goldsky import SentinelGoldsky, StrategyDirectoryRow, _to_candidate
from sentinel.onchain import OnChainRunner
from sentinel.state import AllocationState, SentinelEvent, SentinelStore, UserState, now_ts

_log = structlog.get_logger(__name__)

# When NAV climbs > 5% above the per-allocation HWM, opportunistically
# settle the strategy fee. Smaller bumps stay un-crystallized to keep
# gas costs bounded.
FEE_THRESHOLD_BPS = 500


@dataclass(frozen=True, slots=True)
class LoopConfig:
    drawdown_check_interval_sec: int = 60
    rank_update_interval_sec: int = 300
    fee_check_interval_sec: int = 300


class SentinelLoop:
    def __init__(
        self,
        store: SentinelStore,
        allocator: SentinelAllocator,
        goldsky: SentinelGoldsky,
        onchain: OnChainRunner,
        config: LoopConfig | None = None,
    ) -> None:
        self._store = store
        self._allocator = allocator
        self._goldsky = goldsky
        self._onchain = onchain
        self._cfg = config or LoopConfig()
        self._candidates: list[StrategyCandidate] = []
        # PR5 (item 21): keep the directory rows alongside the candidates
        # so `/v1/strategies` can read from the same cache rather than
        # re-querying Goldsky on every dashboard request. Both are derived
        # from the same `fetch_directory()` payload — refreshing one
        # refreshes the other on the `rank_update_interval_sec` cadence.
        self._directory: list[StrategyDirectoryRow] = []
        self._last_rank_ts: int = 0
        self._last_fee_ts: int = 0
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    # ── Lifecycle ──────────────────────────────────────────────
    def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="sentinel.loop")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None
        await self._goldsky.aclose()

    async def _run(self) -> None:
        while not self._stop.is_set():
            await self.tick_once()
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=self._cfg.drawdown_check_interval_sec
                )
            except TimeoutError:
                continue

    # ── Tick ──────────────────────────────────────────────────
    async def tick_once(self, now: int | None = None) -> None:
        ts = now if now is not None else now_ts()
        await self._refresh_candidates(ts)
        for user in self._store.all_users():
            await self._tick_user(user, ts)

    async def _refresh_candidates(self, ts: int) -> None:
        if ts - self._last_rank_ts < self._cfg.rank_update_interval_sec:
            return
        try:
            rows = await self._goldsky.fetch_directory()
            self._directory = rows
            self._candidates = [_to_candidate(r) for r in rows]
            self._last_rank_ts = ts
            _log.info("sentinel.candidates.refresh", count=len(self._candidates))
        except Exception as exc:
            _log.warning("sentinel.candidates.error", err=str(exc), exc_info=True)

    async def directory(self, ts: int | None = None) -> list[StrategyDirectoryRow]:
        """Cached directory rows for `/v1/strategies`. Refreshes lazily on the
        same `rank_update_interval_sec` cadence as the loop itself, so dashboard
        loads no longer hit Goldsky per request."""
        await self._refresh_candidates(ts if ts is not None else now_ts())
        return list(self._directory)

    async def _tick_user(self, user: UserState, ts: int) -> None:
        # Step 4: drawdown check first — before any rebalancing logic.
        await self._enforce_drawdown(user, ts)

        # Steps 1+2: rank + target allocation, gated on rebalance cadence.
        if self._should_rebalance(user, ts):
            target = self._compute_target(user)
            ops = self._diff(user, target)
            if ops:
                await self._apply_diffs(user, target, ops, ts)
                user.last_rebalance_ts = ts

        # Step 6: fee crystallization, opportunistic.
        if ts - self._last_fee_ts >= self._cfg.fee_check_interval_sec:
            await self._maybe_settle_fees(user, ts)
            self._last_fee_ts = ts

    # ── Step 4: drawdown ───────────────────────────────────────
    async def _enforce_drawdown(self, user: UserState, ts: int) -> None:
        threshold = user.meta.drawdown_threshold_bps
        for alloc in list(user.allocations.values()):
            if alloc.defunded or alloc.capital_deployed_usd == 0:
                continue
            if alloc.drawdown_bps >= threshold > 0:
                # Async wrapper keeps the event loop draining while
                # `wait_for_transaction_receipt(timeout=30)` blocks the
                # underlying Web3 call — otherwise every WS subscriber
                # and the drawdown poll itself stall for up to 30s.
                await self._onchain.defund_async(
                    user.meta.user_address, alloc.strategy_id, "DRAWDOWN_BREACH"
                )
                alloc.defunded = True
                self._store.emit_event(
                    SentinelEvent(
                        user_address=user.meta.user_address,
                        kind="STRATEGY_DEFUNDED",
                        strategy_id=alloc.strategy_id,
                        amount_usd=alloc.capital_deployed_usd,
                        reason="DRAWDOWN_BREACH",
                        timestamp=ts,
                    )
                )

    # ── Steps 1+2: rank + target ──────────────────────────────
    def _should_rebalance(self, user: UserState, ts: int) -> bool:
        if user.last_rebalance_ts == 0:
            return True  # first cycle — always allocate idle capital
        cadence = max(60, user.meta.rebalance_cadence_sec)
        return ts - user.last_rebalance_ts >= cadence

    def _compute_target(self, user: UserState) -> list[AllocationTarget]:
        if user.delegated_capital_usd <= 0:
            return []
        candidates = list(self._candidates)
        if not candidates:
            return []
        scores = self._allocator.rank_strategies(user.meta, candidates)
        # Best-first ordering — `allocate` truncates at max_strategies_count.
        order = sorted(zip(candidates, scores, strict=True), key=lambda p: p[1], reverse=True)
        ranked = [c for c, _ in order]
        return self._allocator.allocate(user.meta, ranked, user.delegated_capital_usd)

    def _diff(
        self,
        user: UserState,
        target: list[AllocationTarget],
    ) -> list[tuple[str, int]]:
        current = {
            sid: a.capital_deployed_usd for sid, a in user.allocations.items() if not a.defunded
        }
        return diff_allocations(current, target)

    # ── Step 5: apply diffs ───────────────────────────────────
    async def _apply_diffs(
        self,
        user: UserState,
        target: list[AllocationTarget],
        ops: list[tuple[str, int]],
        ts: int,
    ) -> None:
        target_by_id = {t.strategy_id: t for t in target}

        # Fast-path: pure in-place redistribution. When every touched
        # strategy keeps a non-zero allocation and the sum of deltas is
        # zero (capital moves between live strategies, no idle in/out),
        # batch the diffs into a single `rebalance(weights_bps)` call.
        # The contract preserves total deployed across the listed
        # strategies, so this is the optimal path for the
        # winner-takes-more-from-loser case where the prior implementation
        # defunded the loser entirely. Note: rebalance() cannot pull
        # capital back to idle, so any decrease that targets zero
        # capital still takes the per-op defund path below.
        if self._is_pure_redistribution(user, ops, target_by_id):
            # AllocatorVault.rebalance asserts sum(weights_bps) == 10_000.
            # The score-weighted allocator can drop ≤ N USD as rounding
            # remainder so the raw weights occasionally sum to 9_999;
            # absorb the slack onto the largest weight so the contract
            # check passes without changing target ratios materially.
            weights = [t.weight_bps for t in target]
            slack = 10_000 - sum(weights)
            if slack != 0:
                largest = max(range(len(weights)), key=lambda i: weights[i])
                weights[largest] += slack
            await self._onchain.rebalance_async(
                user.meta.user_address,
                [t.strategy_id for t in target],
                weights,
            )
            for t in target:
                alloc = user.allocations.get(t.strategy_id)
                if alloc is None:
                    continue
                prior = alloc.capital_deployed_usd
                alloc.capital_deployed_usd = t.capital_usd
                alloc.last_rebalance_ts = ts
                if t.capital_usd == prior:
                    continue
                kind = "ALLOCATION_INCREASED" if t.capital_usd > prior else "ALLOCATION_DECREASED"
                self._store.emit_event(
                    SentinelEvent(
                        user_address=user.meta.user_address,
                        kind=kind,  # type: ignore[arg-type]
                        strategy_id=t.strategy_id,
                        amount_usd=abs(t.capital_usd - prior),
                        reason="REBALANCE",
                        timestamp=ts,
                    )
                )
            self._emit_rebalance_complete(user, ts)
            return

        for strategy_id, delta in ops:
            if delta > 0:
                await self._onchain.allocate_async(user.meta.user_address, strategy_id, delta)
                tgt = target_by_id.get(strategy_id)
                chain_id = tgt.chain_id if tgt else 0
                kind: str
                if strategy_id in user.allocations and not user.allocations[strategy_id].defunded:
                    user.allocations[strategy_id].capital_deployed_usd += delta
                    kind = "ALLOCATION_INCREASED"
                else:
                    declared = self._declared_class(strategy_id)
                    user.allocations[strategy_id] = AllocationState(
                        strategy_id=strategy_id,
                        chain_id=chain_id,
                        declared_class=declared,
                        capital_deployed_usd=delta,
                        high_water_mark_usd=delta,
                        nav_usd=delta,
                        last_rebalance_ts=ts,
                    )
                    kind = "ALLOCATION_CREATED"
                self._store.emit_event(
                    SentinelEvent(
                        user_address=user.meta.user_address,
                        kind=kind,  # type: ignore[arg-type]
                        strategy_id=strategy_id,
                        amount_usd=delta,
                        reason="REBALANCE",
                        timestamp=ts,
                    )
                )
            else:
                # Decrease where target_capital == 0 OR the kept set
                # changes shape (idle goes up). The rebalance fast-path
                # above already absorbed pure redistribution; remaining
                # decreases need a defund because rebalance() cannot
                # repatriate capital to idle.
                await self._onchain.defund_async(user.meta.user_address, strategy_id, "RANK_DROP")
                if strategy_id in user.allocations:
                    user.allocations[strategy_id].defunded = True
                self._store.emit_event(
                    SentinelEvent(
                        user_address=user.meta.user_address,
                        kind="STRATEGY_DEFUNDED",
                        strategy_id=strategy_id,
                        amount_usd=-delta,
                        reason="RANK_DROP",
                        timestamp=ts,
                    )
                )
        self._emit_rebalance_complete(user, ts)

    def _is_pure_redistribution(
        self,
        user: UserState,
        ops: list[tuple[str, int]],
        target_by_id: dict[str, AllocationTarget],
    ) -> bool:
        """True iff `ops` redistribute capital between currently-live
        strategies without changing total deployed.

        Conditions:
          - every op's strategy is in target with `capital_usd > 0`
            (no full removals, no idle-bound shrinkage);
          - every op's strategy already has a live, non-defunded
            allocation (rebalance() can only redistribute existing
            deployed capital);
          - net delta is at most one USD unit per touched strategy
            (rebalance() preserves total deployed; integer-division
            in the score-weighted allocator drops up to N USD as
            rounding remainder, which we treat as idle within
            tolerance).
        """
        if not ops:
            return False
        net = 0
        touched = 0
        for sid, delta in ops:
            tgt = target_by_id.get(sid)
            if tgt is None or tgt.capital_usd == 0:
                return False
            alloc = user.allocations.get(sid)
            if alloc is None or alloc.defunded or alloc.capital_deployed_usd == 0:
                return False
            net += delta
            touched += 1
        return abs(net) <= touched

    def _emit_rebalance_complete(self, user: UserState, ts: int) -> None:
        self._store.emit_event(
            SentinelEvent(
                user_address=user.meta.user_address,
                kind="REBALANCE_COMPLETE",
                strategy_id=None,
                amount_usd=user.delegated_capital_usd,
                reason="",
                timestamp=ts,
            )
        )

    # ── Step 6: fees ──────────────────────────────────────────
    async def _maybe_settle_fees(self, user: UserState, ts: int) -> None:
        for alloc in user.allocations.values():
            if alloc.defunded or alloc.high_water_mark_usd == 0:
                continue
            threshold = alloc.high_water_mark_usd * (10_000 + FEE_THRESHOLD_BPS) // 10_000
            if alloc.nav_usd >= threshold:
                await self._onchain.settle_fee_async(user.meta.user_address, alloc.strategy_id)
                alloc.high_water_mark_usd = alloc.nav_usd
                self._store.emit_event(
                    SentinelEvent(
                        user_address=user.meta.user_address,
                        kind="FEE_SETTLED",
                        strategy_id=alloc.strategy_id,
                        amount_usd=alloc.nav_usd,
                        reason="HWM_BREACH",
                        timestamp=ts,
                    )
                )

    # ── Helpers ───────────────────────────────────────────────
    def _declared_class(self, strategy_id: str) -> str:
        for c in self._candidates:
            if c.strategy_id == strategy_id:
                return c.declared_class
        return ""

    @property
    def candidates(self) -> list[StrategyCandidate]:
        return list(self._candidates)

    def seed_candidates(self, candidates: Iterable[StrategyCandidate]) -> None:
        """Used by tests + scenario mode to inject candidates without HTTP."""
        self._candidates = list(candidates)
        self._last_rank_ts = int(time.time())

    def seed_directory(self, rows: Iterable[StrategyDirectoryRow]) -> None:
        """Test/scenario hook to seed `/v1/strategies` cache without HTTP."""
        self._directory = list(rows)
        self._last_rank_ts = int(time.time())
