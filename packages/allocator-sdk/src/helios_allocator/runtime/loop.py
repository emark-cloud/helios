"""AllocatorLoop — the SDK's generalized decision loop.

Mirrors `Helios.md §11.2`'s six-step cycle:

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

Generalized from `services/sentinel/src/sentinel/loop.py` so any
`BaseAllocator` subclass (Sentinel, Helix, third-party) shares the
runtime. The allocator itself only supplies `rank_strategies` and
`allocate`; everything else is loop machinery.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import structlog

from helios_allocator.base import BaseAllocator
from helios_allocator.runtime.goldsky import (
    AllocatorGoldsky,
    MultiChainAllocatorGoldsky,
    StrategyDirectoryRow,
    to_candidate,
)
from helios_allocator.runtime.onchain import AllocatorOnChain
from helios_allocator.runtime.state import (
    AllocationState,
    AllocatorEvent,
    AllocatorStore,
    UserState,
    now_ts,
)
from helios_allocator.types import AllocationTarget, StrategyCandidate

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
    # Drop strategies from the candidate set when their most recent
    # NAV snapshot is older than this. The protocol requires a live
    # navOracle signer to keep posting NAVs as the operator drives the
    # vault — a strategy whose oracle has gone silent shouldn't keep
    # receiving capital just because its registry row is `active=true`.
    # 0 disables the filter (back-compat for backtests / scenario mode
    # that have no NAV snapshots).
    nav_freshness_sec: int = 3600


class AllocatorLoop:
    def __init__(
        self,
        store: AllocatorStore,
        allocator: BaseAllocator,
        # `MultiChainAllocatorGoldsky` is structurally a drop-in
        # replacement (`fetch_directory`, `fetch_candidates`, `aclose`)
        # — the loop never touches single-chain-only fields. The union
        # lets Sentinel/Helix swap a single-endpoint client for a
        # tri-chain fan-out without changing this contract.
        goldsky: AllocatorGoldsky | MultiChainAllocatorGoldsky,
        onchain: AllocatorOnChain,
        config: LoopConfig | None = None,
    ) -> None:
        self._store = store
        self._allocator = allocator
        self._goldsky = goldsky
        self._onchain = onchain
        self._cfg = config or LoopConfig()
        self._candidates: list[StrategyCandidate] = []
        # Keep the directory rows alongside the candidates so
        # `/v1/strategies` can read from the same cache rather than
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
        self._task = asyncio.create_task(self._run(), name="allocator.loop")

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
            # If the subgraph's NAVSnapshot index is empty (e.g., the
            # subgraph version predates a fresh vault deployment), fall
            # back to reading `StrategyVault.lastNAVTimestamp()` over
            # RPC. The on-chain getter is the source of truth anyway —
            # the subgraph is just a faster cache when warm.
            if self._cfg.nav_freshness_sec > 0 and self._onchain.live:
                rows = await self._enrich_nav_timestamps(rows)
            self._directory = rows
            # Filter to strategies whose navOracle is actively posting.
            # `nav_freshness_sec == 0` disables (back-compat for scenarios
            # without a NAV stream); otherwise a row is eligible only if
            # its most recent NAV snapshot is within the freshness budget.
            # A strategy that has never NAV-reported is excluded — the
            # protocol's runtime contract is that the navOracle signer
            # MUST publish on operator start, so a missing signal means
            # nobody is driving the vault and capital would just stagnate.
            budget = self._cfg.nav_freshness_sec
            if budget <= 0:
                eligible = rows
            else:
                eligible = [
                    r
                    for r in rows
                    if r.last_nav_update_ts > 0 and ts - r.last_nav_update_ts <= budget
                ]
            dropped = len(rows) - len(eligible)
            self._candidates = [to_candidate(r) for r in eligible]
            self._last_rank_ts = ts
            _log.info(
                "allocator.candidates.refresh",
                count=len(self._candidates),
                dropped_stale_nav=dropped,
            )
        except Exception as exc:
            _log.warning("allocator.candidates.error", err=str(exc), exc_info=True)

    async def _enrich_nav_timestamps(
        self, rows: list[StrategyDirectoryRow]
    ) -> list[StrategyDirectoryRow]:
        # Concurrently look up `lastNAVTimestamp` for any row the subgraph
        # didn't already supply. Bounded fan-out: at most ~20 strategies
        # in the testnet directory, one eth_call each, ~50 ms apiece.
        targets = [(i, r) for i, r in enumerate(rows) if r.last_nav_update_ts == 0]
        if not targets:
            return rows
        ts_results = await asyncio.gather(
            *(self._onchain.read_strategy_nav_timestamp_async(r.strategy_id) for _, r in targets),
            return_exceptions=True,
        )
        enriched = list(rows)
        for (i, _), result in zip(targets, ts_results, strict=True):
            if isinstance(result, BaseException) or result is None:
                continue
            r = enriched[i]
            enriched[i] = StrategyDirectoryRow(
                strategy_id=r.strategy_id,
                declared_class=r.declared_class,
                chain_id=r.chain_id,
                operator=r.operator,
                fee_rate_bps=r.fee_rate_bps,
                stake_amount_usd=r.stake_amount_usd,
                max_capacity_usd=r.max_capacity_usd,
                current_allocations_usd=r.current_allocations_usd,
                reputation_score_e4=r.reputation_score_e4,
                trades_attested=r.trades_attested,
                last_nav_update_ts=int(result),
            )
        return enriched

    async def directory(self, ts: int | None = None) -> list[StrategyDirectoryRow]:
        """Cached directory rows for `/v1/strategies`. Refreshes lazily on the
        same `rank_update_interval_sec` cadence as the loop itself, so dashboard
        loads no longer hit Goldsky per request."""
        await self._refresh_candidates(ts if ts is not None else now_ts())
        return list(self._directory)

    async def _tick_user(self, user: UserState, ts: int) -> None:
        # Refresh `delegated_capital_usd` from on-chain UserVault balance.
        # `_compute_target` gates on this — without an RPC seed it stays
        # zero (the upsert path doesn't write it) and no allocation ever
        # fires. Reading on every tick also handles deposit/withdraw
        # cycles transparently. RPC errors leave the prior value in
        # place; stub mode (no UserVault address configured) returns
        # None and we fall back to whatever the meta-strategy POST or a
        # test fixture seeded.
        try:
            balance = await self._onchain.read_user_vault_balance_async(user.meta.user_address)
        except Exception as exc:  # pragma: no cover — defensive RPC guard
            _log.warning(
                "allocator.user_vault_balance.error",
                user=user.meta.user_address,
                err=str(exc),
            )
            balance = None
        if balance is not None:
            user.delegated_capital_usd = balance

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
            # Record the current NAV in the TWAP ring even when no chain
            # mirror has happened this tick — otherwise a defund decision
            # taken seconds after a flash bar would still see only the
            # spike value. AllocatorStore preserves the ring across mirror
            # updates (HIGH #14 in `docs/phase-3-review.md`).
            alloc.nav_samples.append((ts, alloc.nav_usd))
            if alloc.twap_drawdown_bps >= threshold > 0:
                # Async wrapper keeps the event loop draining while
                # `wait_for_transaction_receipt(timeout=30)` blocks the
                # underlying Web3 call — otherwise every WS subscriber
                # and the drawdown poll itself stall for up to 30s.
                call = await self._onchain.defund_async(
                    user.meta.user_address, alloc.strategy_id, "DRAWDOWN_BREACH"
                )
                alloc.defunded = True
                self._store.emit_event(
                    AllocatorEvent(
                        user_address=user.meta.user_address,
                        kind="STRATEGY_DEFUNDED",
                        strategy_id=alloc.strategy_id,
                        amount_usd=alloc.capital_deployed_usd,
                        reason="DRAWDOWN_BREACH",
                        timestamp=ts,
                        tx_hash=call.tx_hash,
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
        return _diff_allocations(current, target)

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
        # Drop remote-chain ops up-front: until the CXR-0a (mUSDC OFT
        # adapter) and CXR-0b (BridgeReceiver + AllocatorVault impl
        # upgrade) on-chain pipe lands, the loop has no way to move
        # capital cross-chain. Each remote op fires a
        # `CROSS_CHAIN_ALLOCATION_DEFERRED` event so the dashboard can
        # show "Sentinel wants to allocate $X to mom.base — pending
        # bridge bring-up" without the local AllocatorVault reverting
        # `StrategyNotRegistered` on a foreign strategyId. Done before
        # the rebalance fast-path because `AllocatorVault.rebalance`
        # iterates the strategies list and would revert on the first
        # remote one — fast-path is local-only by construction.
        ops = self._defer_remote_ops(user, ops, target_by_id, ts)

        if self._is_pure_redistribution(user, ops, target_by_id):
            # AllocatorVault.rebalance asserts sum(weights_bps) == 10_000.
            # The score-weighted allocator can drop ≤ N USD as rounding
            # remainder so the raw weights occasionally sum to 9_999;
            # absorb the slack onto the largest weight so the contract
            # check passes without changing target ratios materially.
            # Iterate `target_by_id` instead of the original `target` list:
            # `_defer_remote_ops` may have popped remote entries from
            # `target_by_id` (see its docstring), and those entries must
            # NOT enter the on-chain `rebalance` call. The original
            # `target` list is left alone so downstream tx-shape tests
            # / dashboard fixtures still see the full intended split.
            local_targets = [t for t in target if t.strategy_id in target_by_id]
            weights = [t.weight_bps for t in local_targets]
            slack = 10_000 - sum(weights)
            if slack != 0:
                largest = max(range(len(weights)), key=lambda i: weights[i])
                weights[largest] += slack
            rebal_call = await self._onchain.rebalance_async(
                user.meta.user_address,
                [t.strategy_id for t in local_targets],
                weights,
            )
            for t in local_targets:
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
                    AllocatorEvent(
                        user_address=user.meta.user_address,
                        kind=kind,  # type: ignore[arg-type]
                        strategy_id=t.strategy_id,
                        amount_usd=abs(t.capital_usd - prior),
                        reason="REBALANCE",
                        timestamp=ts,
                        tx_hash=rebal_call.tx_hash,
                    )
                )
            self._emit_rebalance_complete(user, ts, tx_hash=rebal_call.tx_hash)
            return

        # Defunds first, then allocates. AllocatorVault checks
        # `userActiveStrategyCount + 1 > meta.maxStrategiesCount` on every
        # allocateToStrategy, so when this cycle is swapping strategy A out
        # and strategy B in (count saturated at the cap), the allocate-first
        # ordering trips MetaMaxStrategiesExceeded on B before A's slot is
        # released. Draining first frees the slot for the new allocation.
        ordered_ops = sorted(ops, key=lambda op: 0 if op[1] < 0 else 1)
        for strategy_id, delta in ordered_ops:
            if delta > 0:
                alloc_call = await self._onchain.allocate_async(
                    user.meta.user_address, strategy_id, delta
                )
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
                    AllocatorEvent(
                        user_address=user.meta.user_address,
                        kind=kind,  # type: ignore[arg-type]
                        strategy_id=strategy_id,
                        amount_usd=delta,
                        reason="REBALANCE",
                        timestamp=ts,
                        tx_hash=alloc_call.tx_hash,
                    )
                )
            else:
                # Decrease where target_capital == 0 OR the kept set
                # changes shape (idle goes up). The rebalance fast-path
                # above already absorbed pure redistribution; remaining
                # decreases need a defund because rebalance() cannot
                # repatriate capital to idle.
                defund_call = await self._onchain.defund_async(
                    user.meta.user_address, strategy_id, "RANK_DROP"
                )
                if strategy_id in user.allocations:
                    user.allocations[strategy_id].defunded = True
                self._store.emit_event(
                    AllocatorEvent(
                        user_address=user.meta.user_address,
                        kind="STRATEGY_DEFUNDED",
                        strategy_id=strategy_id,
                        amount_usd=-delta,
                        reason="RANK_DROP",
                        timestamp=ts,
                        tx_hash=defund_call.tx_hash,
                    )
                )
        self._emit_rebalance_complete(user, ts)

    def _defer_remote_ops(
        self,
        user: UserState,
        ops: list[tuple[str, int]],
        target_by_id: dict[str, AllocationTarget],
        ts: int,
    ) -> list[tuple[str, int]]:
        """Strip ops whose target lives on a chain the local
        `AllocatorOnChain` doesn't sign for and emit a deferral event
        per stripped op.

        Returns the remaining (local-only) ops list. A target whose
        `chain_id == 0` (legacy un-tagged Goldsky row, or an untagged
        AllocationTarget from a test fixture) is treated as local —
        otherwise pre-CXR-4 tests + scenario runs would all suddenly
        defer their allocations.

        Side effect: remote entries are popped from `target_by_id` so
        the rebalance fast-path's weights iteration doesn't include
        them. The pure-redistribution check uses `target_by_id` itself
        for the same reason — once an op is stripped, the corresponding
        target must vanish or `AllocatorVault.rebalance` would revert
        on the first cross-chain strategyId.

        Same-chain ops fall through unchanged. The deferred remote ops
        do *not* mutate `user.allocations` — until real capital actually
        bridges, the dashboard should not show them as deployed. The
        repeated emission each cycle is intentional: the deferred state
        is a recurring "still pending" signal, and the loop has no
        tx_hash to dedup against, so consumers can subscribe to the
        kind once and surface the live intended allocation.
        """
        local = self._onchain.chain_id
        kept: list[tuple[str, int]] = []
        for sid, delta in ops:
            tgt = target_by_id.get(sid)
            if tgt is None or tgt.chain_id in (0, local):
                kept.append((sid, delta))
                continue
            # Drop the remote target so downstream paths (rebalance
            # fast-path, _apply_diffs target_by_id lookup for kind
            # tagging) only see local entries.
            target_by_id.pop(sid, None)
            # CXR-0c — try a live remote allocation if the runner has the
            # bridge wired for this destination chain. Fall back to the
            # deferred event on any failure (mis-wired OFT, no LZ fee
            # native gas, revert) so the dashboard still shows intent.
            if delta > 0 and self._onchain.supports_remote_chain(tgt.chain_id):
                try:
                    remote_vault = self._onchain.resolve_remote_vault(sid)
                    call = self._onchain.allocate_to_remote(
                        user.meta.user_address,
                        sid,
                        int(delta),
                        tgt.chain_id,
                        remote_vault,
                    )
                    if not call.error:
                        self._store.emit_event(
                            AllocatorEvent(
                                user_address=user.meta.user_address,
                                kind="CROSS_CHAIN_ALLOCATION_SUBMITTED",
                                strategy_id=sid,
                                amount_usd=delta,
                                reason=f"chain={tgt.chain_id}; OFT send on Kite",
                                timestamp=ts,
                                tx_hash=call.tx_hash,
                            )
                        )
                        _log.info(
                            "allocator.allocation.cross_chain.submitted",
                            user=user.meta.user_address,
                            strategy=sid,
                            amount=delta,
                            dst_chain_id=tgt.chain_id,
                            tx_hash=call.tx_hash,
                        )
                        continue
                    _log.warning(
                        "allocator.allocation.cross_chain.live_failed",
                        user=user.meta.user_address,
                        strategy=sid,
                        amount=delta,
                        dst_chain_id=tgt.chain_id,
                        err=call.error,
                    )
                except Exception as exc:
                    _log.warning(
                        "allocator.allocation.cross_chain.live_exception",
                        user=user.meta.user_address,
                        strategy=sid,
                        amount=delta,
                        dst_chain_id=tgt.chain_id,
                        err=str(exc),
                    )
            # Only emit on the "add capital" direction. A delta<0 against
            # a remote strategy would mean we somehow accounted for a
            # remote allocation locally — currently impossible since we
            # never write user.allocations for remote targets — but the
            # invariant is "remote ops are silent on-chain", not "remote
            # ops are silent in the event log", so we still log the
            # cycle-time intent.
            self._store.emit_event(
                AllocatorEvent(
                    user_address=user.meta.user_address,
                    kind="CROSS_CHAIN_ALLOCATION_DEFERRED",
                    strategy_id=sid,
                    amount_usd=max(0, delta),
                    reason=f"chain={tgt.chain_id}; pending CXR-0a/0b bridge",
                    timestamp=ts,
                )
            )
            _log.info(
                "allocator.allocation.cross_chain.deferred",
                user=user.meta.user_address,
                strategy=sid,
                amount=delta,
                dst_chain_id=tgt.chain_id,
                local_chain_id=local,
            )
        return kept

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

    def _emit_rebalance_complete(self, user: UserState, ts: int, *, tx_hash: str = "") -> None:
        self._store.emit_event(
            AllocatorEvent(
                user_address=user.meta.user_address,
                kind="REBALANCE_COMPLETE",
                strategy_id=None,
                amount_usd=user.delegated_capital_usd,
                reason="",
                timestamp=ts,
                tx_hash=tx_hash,
            )
        )

    # ── Step 6: fees ──────────────────────────────────────────
    async def _maybe_settle_fees(self, user: UserState, ts: int) -> None:
        for alloc in user.allocations.values():
            if alloc.defunded or alloc.high_water_mark_usd == 0:
                continue
            threshold = alloc.high_water_mark_usd * (10_000 + FEE_THRESHOLD_BPS) // 10_000
            if alloc.nav_usd >= threshold:
                fee_call = await self._onchain.settle_fee_async(
                    user.meta.user_address, alloc.strategy_id
                )
                alloc.high_water_mark_usd = alloc.nav_usd
                self._store.emit_event(
                    AllocatorEvent(
                        user_address=user.meta.user_address,
                        kind="FEE_SETTLED",
                        strategy_id=alloc.strategy_id,
                        amount_usd=alloc.nav_usd,
                        reason="HWM_BREACH",
                        timestamp=ts,
                        tx_hash=fee_call.tx_hash,
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


def _diff_allocations(
    current_capital: dict[str, int],
    target: Sequence[AllocationTarget],
) -> list[tuple[str, int]]:
    """Return (strategy, delta) ops needed to move from current to target.

    Invariant: a defund op is emitted only for sids present in
    `current_capital` with non-zero capital. Caller hands us
    `{sid: capital_deployed for sid in user.allocations if not defunded}`,
    so a strategy the user was never allocated to cannot generate a
    defund — closing the `StrategyNotAllocated()` revert path that
    legacy vaults could otherwise reach if they leaked into the diff
    via a different code path. Mirrors
    `services/sentinel/src/sentinel/allocator.diff_allocations`.
    """
    ops: list[tuple[str, int]] = []
    seen: set[str] = set()
    for t in target:
        seen.add(t.strategy_id)
        delta = t.capital_usd - current_capital.get(t.strategy_id, 0)
        if delta != 0:
            ops.append((t.strategy_id, delta))
    for sid, deployed in current_capital.items():
        if sid in seen or deployed == 0:
            continue
        ops.append((sid, -deployed))  # full removal
    return ops


__all__ = [
    "FEE_THRESHOLD_BPS",
    "AllocatorLoop",
    "LoopConfig",
]
