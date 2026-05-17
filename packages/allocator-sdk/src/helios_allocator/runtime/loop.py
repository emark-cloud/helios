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

# `meta.max_capital_usd` is the user's human-USD figure as signed
# (frontend posts e.g. 1_000); `to_sdk_meta` carries it through
# unscaled. Every on-chain quantity the budget is reconciled against —
# `read_user_vault_balance` and `userTotalDeployed` — is raw 18-dec
# wei (the runtime's canonical scale, mirrored by the config's
# `*_usd_wei` knobs and the on-chain `MetaStrategy.maxCapital`, which
# is `max_capital_usd * 1e18`). Comparing the two requires lifting the
# cap into wei first; without it `min(delegated_wei, cap)` collapses
# the budget to ~`max_capital_usd` wei and every op dust-skips.
_USD_WEI_SCALE = 10**18


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
    # Master switch for live cross-chain *capital* movement (the OFT.send
    # path that burns ~1–1.2 KITE per submit in LZ V2 executor fees).
    # Default False: v1 ships with cross-chain capital flow OFF — the LZ
    # fixed-fee economics make per-rebalance bridging impractical on
    # testnet, so the loop always falls back to the zero-cost
    # `CROSS_CHAIN_ALLOCATION_DEFERRED` event regardless of whether the
    # OFT adapter is wired. This is a deliberate v1 product decision, not
    # a temporary mute: a practical cross-chain capital design is a
    # documented v2 item (see docs/cross-chain-cost-roadmap.md §"v2").
    # Cross-chain *reputation* propagation is a separate, cheap path and
    # is unaffected by this flag. Set True only to exercise the live send
    # path (v2 work / targeted tests).
    cross_chain_capital_enabled: bool = False
    # Cross-chain cost Tier 1 — minimum delta (18-dec USD wei) for a
    # cross-chain allocate to be worth burning the ~1 KITE LZ V2 fixed
    # fee. Smaller deltas get skipped silently and the op rolls into the
    # next tick; eventually accumulated deltas cross the threshold and
    # fire as a single send. Default $10 ≈ 10e18 wei (Kite canonical
    # 18-dec). 0 disables the gate (back-compat for tests / dry-runs).
    min_cross_chain_alloc_usd_wei: int = 10 * 10**18
    # Cross-chain cost Tier 1 — minimum seconds between consecutive
    # cross-chain submits for the same (user, strategyId). Prevents
    # 60s-tick spam from firing a fresh LZ V2 send each cycle when the
    # target oscillates; only the post-window net delta fires. Default
    # 300s. 0 disables the gate.
    cross_chain_flush_cadence_sec: int = 300
    # Local (same-chain) anti-dust-churn floor: minimum |delta| (asset
    # wei) for an allocate/defund op to actually execute on-chain. An
    # allocate→defund round-trip costs ~10 bps of swap spread plus the
    # strategy's NAV float-clamp rounding; below that fixed cost the
    # move is strictly value-destructive, so sub-floor ops are dropped
    # (the capital stays where it is — dust is not worth a tx). This
    # also breaks the cold-start churn loop once scores diverge by
    # epsilon and the incumbency tie-break in `_compute_target` no
    # longer fully pins the set. Default 0 (disabled) — the SDK can't
    # assume the consumer's asset decimals, so the real floor is opted
    # in by the deployment: Sentinel sets it from
    # `SENTINEL_MIN_LOCAL_ALLOC_USD_WEI` (1e15 = 0.001 mUSDC on Kite's
    # 18-dec scale). Mirrors the `min_cross_chain_alloc_usd_wei`
    # convention (0 = back-compat for tests / scenario mode).
    min_local_alloc_usd_wei: int = 0


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
        # Cross-chain cost Tier 1 — per-(user, strategyId) timestamp of
        # the last successful cross-chain submit. Read in
        # `_defer_remote_ops` to enforce `cross_chain_flush_cadence_sec`
        # spacing between LZ V2 sends. Unbounded growth is fine: one
        # entry per (user, strategyId) pair the loop ever submits for,
        # which scales with active subscribers × cross-chain strategies.
        self._cross_chain_last_fire: dict[tuple[str, str], int] = {}
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
        # On-chain aggregate principal already routed for this user
        # (`userTotalDeployed`). Read this FIRST: the UserVault balance
        # below is the *liquid* balance — it excludes anything already
        # deployed to strategies — so the user's true total delegation
        # is liquid + deployed. The AllocatorVault meta-capital cap
        # (`userTotalDeployed + newAmount <= meta.maxCapital`) is also
        # enforced against this, so `_compute_target` needs it for
        # orphan headroom. None (stub / RPC failure) → treated as zero
        # downstream.
        try:
            on_chain_deployed = await self._onchain.read_user_total_deployed_async(
                user.meta.user_address
            )
        except Exception as exc:  # pragma: no cover — defensive RPC guard
            _log.warning(
                "allocator.user_total_deployed.error",
                user=user.meta.user_address,
                err=str(exc),
            )
            on_chain_deployed = None

        # Refresh `delegated_capital_usd` from the on-chain UserVault
        # balance. `read_user_vault_balance` returns the *liquid*
        # balance — it shrinks as capital is routed out to strategies —
        # so the user's true total delegation is `liquid +
        # userTotalDeployed`. Budgeting against the liquid remainder
        # alone tears every funded allocation down the moment the RPC
        # returns a consistent non-zero deployed read (target ≪ current
        # → full-removal diff), then re-allocates next cadence: a
        # defund/realloc churn loop that bleeds swap spread + gas and
        # never durably deploys (a flaky RPC intermittently reading
        # deployed=0 had been masking this). `_compute_target` gates on
        # this value — without an RPC seed it stays zero (the upsert
        # path doesn't write it) and no allocation ever fires. Reading
        # every tick also handles deposit/withdraw transparently. RPC
        # errors leave the prior value; stub mode (no UserVault address)
        # returns None and we keep whatever the meta-strategy POST or a
        # test fixture seeded (already the total there, not liquid).
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
            user.delegated_capital_usd = balance + (on_chain_deployed or 0)

        _log.info(
            "allocator.tick_user",
            user=user.meta.user_address,
            balance=str(balance) if balance is not None else "none",
            delegated=str(user.delegated_capital_usd),
            on_chain_deployed=str(on_chain_deployed) if on_chain_deployed is not None else "none",
            allocations=len(user.allocations),
            last_rebalance_ts=user.last_rebalance_ts,
        )

        # Step 4: drawdown check first — before any rebalancing logic.
        await self._enforce_drawdown(user, ts)

        # Steps 1+2: rank + target allocation, gated on rebalance cadence.
        if self._should_rebalance(user, ts):
            target = self._compute_target(user, on_chain_deployed)
            ops = self._filter_dust_ops(user, self._diff(user, target))
            _log.info(
                "allocator.tick_user.diff",
                user=user.meta.user_address,
                targets=len(target),
                ops=len(ops),
                candidate_count=len(self._candidates),
            )
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
                # Fix #2 — if the drawdown defund reverted the position
                # is still live and still in breach; leave `defunded`
                # False so the next tick retries instead of marking it
                # closed off a failed call.
                if call.error:
                    _log.warning(
                        "allocator.drawdown_defund.onchain_rejected",
                        user=user.meta.user_address,
                        strategy=alloc.strategy_id,
                    )
                    continue
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

    def _compute_target(
        self, user: UserState, on_chain_deployed: int | None
    ) -> list[AllocationTarget]:
        if user.delegated_capital_usd <= 0:
            return []
        candidates = list(self._candidates)
        # Fix #4 — respect the user's signed `allowed_chains`. A
        # candidate on a chain outside the meta-strategy mandate must
        # never become a target (no local submit, no cross-chain defer,
        # no bridge). `chain_id == 0` is a legacy / untagged Goldsky row
        # and is treated as local-and-allowed so pre-CXR fixtures keep
        # working. An empty `allowed_chains` disables the gate (older
        # meta payloads that never carried the field).
        allowed = {int(c) for c in user.meta.allowed_chains}
        if allowed:
            candidates = [c for c in candidates if c.chain_id == 0 or c.chain_id in allowed]
        if not candidates:
            return []

        # Fix #1 + #3 — size within the on-chain meta-capital headroom.
        # `delegated_capital_usd` is the user's *total* delegation
        # (`_tick_user` reconstitutes it as liquid UserVault balance +
        # `userTotalDeployed`; on the stub/None path it is the seeded
        # total). `BaseAllocator.allocate` derives the per-strategy cap
        # as `capital * maxPerStrategyBps / 1e4`; the on-chain check
        # uses `maxCapital * maxPerStrategyBps / 1e4`. Passing the raw
        # UserVault balance (which can exceed maxCapital) would breach
        # *both* the aggregate and per-strategy on-chain caps. Clamp to
        # maxCapital, then subtract the orphaned on-chain principal
        # (deployed under a prior onboard, untracked by this store —
        # our own `managed` deployed capital is already inside the
        # total) so `userTotalDeployed + sum(new) <= maxCapital` holds.
        # `maxCapital <= 0` means uncapped (mirrors the StrategyVault
        # capacity convention) → balance-only sizing.
        cap = user.meta.max_capital_usd * _USD_WEI_SCALE
        budget = min(user.delegated_capital_usd, cap) if cap > 0 else user.delegated_capital_usd
        if on_chain_deployed is not None:
            managed = sum(
                a.capital_deployed_usd for a in user.allocations.values() if not a.defunded
            )
            orphaned = max(0, on_chain_deployed - managed)
            budget = max(0, budget - orphaned)
        if budget <= 0:
            return []

        scores = self._allocator.rank_strategies(user.meta, candidates)
        # Best-first ordering — `allocate` truncates at max_strategies_count.
        #
        # The sort key is fully deterministic and incumbency-sticky:
        # (score, currently-funded, strategy_id), all descending. The
        # secondary keys only matter when `score` ties — which is the
        # cold-start steady state: every strategy sits at the baseline
        # reputation with ~0 NAV, so `rank_strategies` returns identical
        # scores for all of them. A plain stable sort then preserves
        # whatever order Goldsky happened to return the candidates in,
        # which reshuffles every refresh → the kept top-N flaps → a
        # funded strategy drops out for one cadence and is defunded
        # (RANK_DROP), then re-allocated next cadence. Each round-trip
        # bleeds principal (swap spread + NAV-clamp rounding), so the
        # flap is actively value-destructive, not just noisy. Preferring
        # the incumbent on a tie pins the kept set until a challenger
        # *genuinely* outscores it, with no tuned margin.
        incumbents = {sid for sid, a in user.allocations.items() if not a.defunded}
        order = sorted(
            zip(candidates, scores, strict=True),
            key=lambda p: (p[1], p[0].strategy_id in incumbents, p[0].strategy_id),
            reverse=True,
        )
        ranked = [c for c, _ in order]
        return self._allocator.allocate(user.meta, ranked, budget)

    def _diff(
        self,
        user: UserState,
        target: list[AllocationTarget],
    ) -> list[tuple[str, int]]:
        current = {
            sid: a.capital_deployed_usd for sid, a in user.allocations.items() if not a.defunded
        }
        return _diff_allocations(current, target)

    def _filter_dust_ops(
        self, user: UserState, ops: list[tuple[str, int]]
    ) -> list[tuple[str, int]]:
        """Drop ops below `min_local_alloc_usd_wei`.

        An allocate/defund round-trip costs more (swap spread +
        NAV-clamp rounding) than a sub-floor delta is worth, so moving
        it on-chain destroys value. Skipping leaves the capital where it
        is — dust is harmless parked; it is not harmless churned. This
        is the second half of the anti-churn fix: the incumbency
        tie-break pins the set while scores are exactly tied, and this
        floor absorbs the residual once dust NAV makes scores diverge by
        epsilon. 0 disables (tests / scenario mode)."""
        floor = self._cfg.min_local_alloc_usd_wei
        if floor <= 0:
            return ops
        kept: list[tuple[str, int]] = []
        for sid, delta in ops:
            if abs(delta) < floor:
                _log.info(
                    "allocator.allocation.dust_skip",
                    user=user.meta.user_address,
                    strategy=sid,
                    delta=str(delta),
                    floor=floor,
                )
                continue
            kept.append((sid, delta))
        return kept

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

        if await self._try_rebalance_fastpath(user, target, ops, target_by_id, ts):
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
                # Fix #2 — only mirror into the store when the chain
                # accepted the call. A reverted allocate (e.g.
                # MetaCapacityExceeded on a re-onboard) previously still
                # bumped `capital_deployed_usd`, so the dashboard showed
                # capital that never landed on-chain. `_submit` already
                # logged `allocator.onchain.submit_failed`; skip the
                # mirror so the store stays reconciled with the chain.
                if alloc_call.error:
                    _log.warning(
                        "allocator.allocation.onchain_rejected",
                        user=user.meta.user_address,
                        strategy=strategy_id,
                        amount=str(delta),
                        method="allocateToStrategy",
                    )
                    continue
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
                # Fix #2 — a reverted defund leaves the capital deployed
                # on-chain; don't flip `defunded` (it would orphan the
                # position from the loop's view and skew the next diff).
                if defund_call.error:
                    _log.warning(
                        "allocator.allocation.onchain_rejected",
                        user=user.meta.user_address,
                        strategy=strategy_id,
                        amount=str(-delta),
                        method="defund",
                    )
                    continue
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

    async def _try_rebalance_fastpath(
        self,
        user: UserState,
        target: list[AllocationTarget],
        ops: list[tuple[str, int]],
        target_by_id: dict[str, AllocationTarget],
        ts: int,
    ) -> bool:
        """Fast-path: pure in-place redistribution. When every touched
        strategy keeps a non-zero allocation and the deltas sum to zero
        (capital moves between live strategies, no idle in/out), batch
        the diffs into one `rebalance(weights_bps)` call. The contract
        preserves total deployed across the listed strategies, so this
        is optimal for the winner-takes-more-from-loser case. Returns
        True when it handled the cycle (caller must not fall through to
        the per-op path); False to defer to per-op allocate/defund.
        """
        if not self._is_pure_redistribution(user, ops, target_by_id):
            return False
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
        # Fix #2 — a reverted rebalance changed nothing on-chain;
        # don't rewrite `capital_deployed_usd` to the intended
        # targets or the store diverges from the chain and the next
        # diff is computed off fiction.
        if rebal_call.error:
            _log.warning(
                "allocator.rebalance.onchain_rejected",
                user=user.meta.user_address,
                strategies=[t.strategy_id for t in local_targets],
            )
            return True
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
        return True

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
        # Tier 2 — collect eligible remote ops by dst_chain_id so a
        # single OFT.send can carry N strategies whose targets share a
        # destination chain (mom.base + mr.base → 1 send instead of 2,
        # saves a fixed-cost LZ V2 fee). Entries shape:
        # `(sid, delta, remote_vault)`.
        eligible: dict[int, list[tuple[str, int, str]]] = {}
        # Ops the loop couldn't submit (mis-wired bridge, defund delta,
        # vault-resolution failure). Each one re-emits its DEFERRED
        # event after batch flush.
        deferred: list[tuple[str, int, int]] = []  # (sid, delta, chain_id)

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
            #
            # `cross_chain_capital_enabled` is the v1 master kill-switch:
            # when False (the default / v1 ship state) the live OFT.send
            # is never attempted even if the adapter is fully wired, so
            # every remote op deterministically becomes a zero-cost
            # DEFERRED event. v1 = cross-chain capital OFF by decision;
            # practical cross-chain capital is a v2 item.
            if not (
                self._cfg.cross_chain_capital_enabled
                and delta > 0
                and self._onchain.supports_remote_chain(tgt.chain_id)
            ):
                deferred.append((sid, delta, tgt.chain_id))
                continue
            # Cross-chain cost Tier 1 — threshold gate. The LZ V2 fee
            # floor on Kite testnet is ~1 KITE per OFT.send regardless
            # of payload size; firing for a $0.50 dust delta burns that
            # fee for negligible reallocation. Skip and let the delta
            # accumulate over subsequent ticks until it crosses the
            # threshold. Threshold-skipped ops are silent (log-only) —
            # the next tick reassesses the cumulative delta.
            if (
                self._cfg.min_cross_chain_alloc_usd_wei > 0
                and delta < self._cfg.min_cross_chain_alloc_usd_wei
            ):
                _log.info(
                    "allocator.allocation.cross_chain.threshold_skip",
                    user=user.meta.user_address,
                    strategy=sid,
                    amount=delta,
                    threshold=self._cfg.min_cross_chain_alloc_usd_wei,
                    dst_chain_id=tgt.chain_id,
                )
                continue
            # Cross-chain cost Tier 1 — per-(user, strategyId) flush
            # cadence. Prevents the 60s tick coordinator from firing a
            # fresh ~1 KITE send every cycle when the target keeps
            # moving by epsilon. The window starts from the last
            # successful submit; ops in the window queue silently and
            # the next-eligible tick fires the net delta.
            key = (user.meta.user_address, sid)
            last_fire = self._cross_chain_last_fire.get(key, 0)
            if (
                self._cfg.cross_chain_flush_cadence_sec > 0
                and last_fire > 0
                and ts - last_fire < self._cfg.cross_chain_flush_cadence_sec
            ):
                _log.info(
                    "allocator.allocation.cross_chain.flush_window",
                    user=user.meta.user_address,
                    strategy=sid,
                    amount=delta,
                    seconds_until_flush=(
                        self._cfg.cross_chain_flush_cadence_sec - (ts - last_fire)
                    ),
                    dst_chain_id=tgt.chain_id,
                )
                continue
            try:
                remote_vault = self._onchain.resolve_remote_vault(sid)
            except Exception as exc:
                _log.warning(
                    "allocator.allocation.cross_chain.vault_resolve_failed",
                    user=user.meta.user_address,
                    strategy=sid,
                    amount=delta,
                    dst_chain_id=tgt.chain_id,
                    err=str(exc),
                )
                deferred.append((sid, delta, tgt.chain_id))
                continue
            eligible.setdefault(tgt.chain_id, []).append((sid, int(delta), remote_vault))

        # Tier 2 — flush each dst_chain_id group: 1 entry uses the
        # single-call path (preserves the existing `RemoteAllocationSent`
        # tx shape + the single-call fee quote); 2+ entries uses the
        # batched compose so the LZ V2 fixed fee is amortized.
        for dst_chain_id, entries in eligible.items():
            failed = self._flush_cross_chain_group(user, dst_chain_id, entries, ts)
            deferred.extend(failed)

        for sid, delta, chain_id in deferred:
            self._emit_cross_chain_deferred(user, sid, delta, chain_id, ts, local)
        return kept

    def _flush_cross_chain_group(
        self,
        user: UserState,
        dst_chain_id: int,
        entries: list[tuple[str, int, str]],
        ts: int,
    ) -> list[tuple[str, int, int]]:
        """Tier 2 — submit `entries` against `dst_chain_id` using the
        single-call path if `len == 1` and the batched path if `len > 1`.

        Returns the entries that fell back to DEFERRED so the caller
        can emit their deferred events alongside the rest.
        """
        if len(entries) == 1:
            sid, delta, remote_vault = entries[0]
            return self._submit_single_remote(user, dst_chain_id, sid, delta, remote_vault, ts)
        return self._submit_batched_remote(user, dst_chain_id, entries, ts)

    def _submit_single_remote(
        self,
        user: UserState,
        dst_chain_id: int,
        sid: str,
        delta: int,
        remote_vault: str,
        ts: int,
    ) -> list[tuple[str, int, int]]:
        try:
            call = self._onchain.allocate_to_remote(
                user.meta.user_address, sid, int(delta), dst_chain_id, remote_vault
            )
        except Exception as exc:
            _log.warning(
                "allocator.allocation.cross_chain.live_exception",
                user=user.meta.user_address,
                strategy=sid,
                amount=delta,
                dst_chain_id=dst_chain_id,
                err=str(exc),
            )
            return [(sid, delta, dst_chain_id)]
        if call.error:
            _log.warning(
                "allocator.allocation.cross_chain.live_failed",
                user=user.meta.user_address,
                strategy=sid,
                amount=delta,
                dst_chain_id=dst_chain_id,
                err=call.error,
            )
            return [(sid, delta, dst_chain_id)]
        self._cross_chain_last_fire[(user.meta.user_address, sid)] = ts
        self._emit_cross_chain_submitted(
            user, sid, delta, dst_chain_id, ts, call.tx_hash, batch_size=1
        )
        return []

    def _submit_batched_remote(
        self,
        user: UserState,
        dst_chain_id: int,
        entries: list[tuple[str, int, str]],
        ts: int,
    ) -> list[tuple[str, int, int]]:
        try:
            call = self._onchain.allocate_to_remote_batch(
                user.meta.user_address, entries, dst_chain_id
            )
        except Exception as exc:
            _log.warning(
                "allocator.allocation.cross_chain.batch_exception",
                user=user.meta.user_address,
                batch_size=len(entries),
                dst_chain_id=dst_chain_id,
                err=str(exc),
            )
            return [(sid, delta, dst_chain_id) for sid, delta, _ in entries]
        if call.error:
            _log.warning(
                "allocator.allocation.cross_chain.batch_failed",
                user=user.meta.user_address,
                batch_size=len(entries),
                dst_chain_id=dst_chain_id,
                err=call.error,
            )
            return [(sid, delta, dst_chain_id) for sid, delta, _ in entries]
        # Happy path — record last_fire + emit per-entry SUBMITTED
        # events sharing the batch's tx_hash. Subgraph consumers group
        # by `transaction.hash`; UI consumers see one event per strategy
        # so the dashboard list stays uniform with the single-call shape.
        for sid, delta, _ in entries:
            self._cross_chain_last_fire[(user.meta.user_address, sid)] = ts
            self._emit_cross_chain_submitted(
                user, sid, delta, dst_chain_id, ts, call.tx_hash, batch_size=len(entries)
            )
        _log.info(
            "allocator.allocation.cross_chain.batch_submitted",
            user=user.meta.user_address,
            batch_size=len(entries),
            dst_chain_id=dst_chain_id,
            tx_hash=call.tx_hash,
            total_amount=sum(d for _, d, _ in entries),
        )
        return []

    def _emit_cross_chain_submitted(
        self,
        user: UserState,
        sid: str,
        delta: int,
        dst_chain_id: int,
        ts: int,
        tx_hash: str,
        *,
        batch_size: int,
    ) -> None:
        reason = (
            f"chain={dst_chain_id}; OFT send on Kite"
            if batch_size == 1
            else f"chain={dst_chain_id}; OFT batch send on Kite (N={batch_size})"
        )
        self._store.emit_event(
            AllocatorEvent(
                user_address=user.meta.user_address,
                kind="CROSS_CHAIN_ALLOCATION_SUBMITTED",
                strategy_id=sid,
                amount_usd=delta,
                reason=reason,
                timestamp=ts,
                tx_hash=tx_hash,
            )
        )
        _log.info(
            "allocator.allocation.cross_chain.submitted",
            user=user.meta.user_address,
            strategy=sid,
            amount=delta,
            dst_chain_id=dst_chain_id,
            tx_hash=tx_hash,
            batch_size=batch_size,
        )

    def _emit_cross_chain_deferred(
        self,
        user: UserState,
        sid: str,
        delta: int,
        chain_id: int,
        ts: int,
        local: int,
    ) -> None:
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
                reason=f"chain={chain_id}; pending CXR-0a/0b bridge",
                timestamp=ts,
            )
        )
        _log.info(
            "allocator.allocation.cross_chain.deferred",
            user=user.meta.user_address,
            strategy=sid,
            amount=delta,
            dst_chain_id=chain_id,
            local_chain_id=local,
        )

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

    @property
    def watched_strategy_ids(self) -> tuple[str, ...]:
        """Active strategy-vault ids the loop currently tracks, as a
        synchronous in-memory snapshot (no I/O). Sourced from the
        Goldsky `active` directory (`_directory`), NOT the NAV-freshness
        filtered candidate set — a temporarily NAV-silent but active
        vault must still be observed for defund / divergence events.
        `chain_watch` reads this so newly deployed strategies are
        watched without env maintenance; the loop owns the refresh
        cadence."""
        return tuple(r.strategy_id for r in self._directory)

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
