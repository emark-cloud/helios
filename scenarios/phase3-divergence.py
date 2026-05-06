"""Phase 3 e2e — Sentinel-vs-Helix divergence scenario (WS7).

Drives both reference allocators in-process against the same synthetic
strategy universe and asserts the four Phase 3 acceptance flows
(`docs/phase3-plan.md` WS7):

  1. **User A picks Sentinel.** Capital flows: a non-empty set of
     `allocateToStrategy` calls is recorded.
  2. **User B picks Helix.** Capital flows AND the resulting
     allocation set is materially different from Sentinel's
     (≥1 strategy in one set is not in the other, OR weights differ
     by ≥5% on a shared strategy).
  3. **Drawdown event on a strategy User A holds.** Sentinel emits
     `defundStrategy` within one tick, with reason DRAWDOWN_BREACH.
  4. **NAV climbs above HWM × 1.05 on a strategy User B holds.**
     Helix emits `settleStrategyFee` within one tick.

This is a **Python in-process scenario** — no anvil, no contracts, no
subgraph. The two allocators compose entirely through the SDK's
`AllocatorRuntime` (`packages/allocator-sdk`); same code paths the
live services run, just driven via stub Goldsky + dry-run on-chain
runner so it ships in CI under a few seconds. Real on-chain
divergence runs against the deploy in `scripts/e2e-phase3.sh` once
`DeployPhase3` lands on a refreshed testnet pin.

Exit codes:
  0 — all four assertions passed
  1 — any assertion failed (the failing one prints to stderr)
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass

from helios_allocator.runtime import (
    AllocationState,
    AllocatorGoldsky,
    AllocatorLoop,
    AllocatorOnChain,
    AllocatorStore,
    LoopConfig,
    StrategyDirectoryRow,
)
from helios_allocator.types import MetaStrategy, StrategyCandidate
from helix.allocator import HelixAllocator
from sentinel.allocator import SentinelAllocator

USER_A = "0x" + "a1" * 20  # picks Sentinel
USER_B = "0x" + "b2" * 20  # picks Helix
CAPITAL = 50_000


@dataclass
class StubRow:
    """Minimal candidate→directory bridge used by the stub goldsky."""

    candidate: StrategyCandidate

    def to_row(self) -> StrategyDirectoryRow:
        c = self.candidate
        return StrategyDirectoryRow(
            strategy_id=c.strategy_id,
            declared_class=c.declared_class,
            chain_id=c.chain_id,
            operator=c.operator,
            fee_rate_bps=c.fee_rate_bps,
            stake_amount_usd=c.stake_amount_usd,
            max_capacity_usd=c.max_capacity_usd,
            current_allocations_usd=c.current_allocations_usd,
            reputation_score_e4=round(c.reputation_score * 10_000),
            trades_attested=c.trades_attested,
        )


class _StubGoldsky(AllocatorGoldsky):
    """Returns canned candidates without HTTP. The same shape Sentinel
    + Helix tests use; lifted here so the scenario is self-contained."""

    def __init__(self, candidates: list[StrategyCandidate]) -> None:
        self._rows = [StubRow(c).to_row() for c in candidates]

    async def fetch_directory(self) -> list[StrategyDirectoryRow]:  # type: ignore[override]
        return list(self._rows)

    async def aclose(self) -> None:
        return None


def _candidate(
    sid_byte: str,
    *,
    declared_class: str = "momentum_v1",
    fee_bps: int,
    rep: float,
    capacity: int = 100_000,
    stake: int = 5_000,
) -> StrategyCandidate:
    return StrategyCandidate(
        strategy_id="0x" + sid_byte * 20,
        declared_class=declared_class,
        chain_id=2368,
        operator="0x" + "cc" * 20,
        fee_rate_bps=fee_bps,
        stake_amount_usd=stake,
        max_capacity_usd=capacity,
        current_allocations_usd=0,
        reputation_score=rep,
        trades_attested=200,
    )


def _user(addr: str, *, drawdown_bps: int = 2_000) -> MetaStrategy:
    return MetaStrategy(
        user_address=addr,
        allowed_strategy_classes=("momentum_v1", "mean_reversion_v1", "yield_rotation_v1"),
        allowed_assets=("USDC", "WKITE"),
        allowed_chains=(2368,),
        max_capital_usd=CAPITAL,
        max_per_strategy_bps=10_000,
        max_strategies_count=3,
        drawdown_threshold_bps=drawdown_bps,
        max_fee_rate_bps=2_500,
        rebalance_cadence_sec=900,
        valid_until=2_000_000_000,
    )


def _build_loop(
    allocator: SentinelAllocator | HelixAllocator,
    candidates: list[StrategyCandidate],
) -> tuple[AllocatorLoop, AllocatorStore, AllocatorOnChain]:
    store = AllocatorStore()
    onchain = AllocatorOnChain(
        rpc_url="",
        operator_pk="",
        allocator_vault_address="",
        allocator_registry_address="",
        chain_id=2368,
    )
    loop = AllocatorLoop(store, allocator, _StubGoldsky(candidates), onchain, config=LoopConfig())
    return loop, store, onchain


def _common_universe() -> list[StrategyCandidate]:
    """Three momentum strategies, identical reputation but staggered fees.
    The fee differential is what separates Helix from Sentinel — Helix's
    continuous fee penalty pulls capital toward cheaper strategies in
    NORMAL regime; Sentinel's binary fee_fit treats them equally."""
    return [
        _candidate("11", fee_bps=200, rep=0.8),  # cheap
        _candidate("22", fee_bps=2_000, rep=0.8),  # pricey
        _candidate("33", fee_bps=800, rep=0.8),  # mid
    ]


# ─── flow 1+2: divergence ──────────────────────────────────


async def assert_divergence() -> dict[str, dict[str, int]]:
    """Drive Sentinel for User A and Helix for User B against the same
    candidate universe. Return both allocation maps."""
    universe = _common_universe()

    sentinel_loop, s_store, s_onchain = _build_loop(SentinelAllocator(), universe)
    helix_loop, h_store, h_onchain = _build_loop(HelixAllocator(), universe)

    user_a = s_store.upsert_user(_user(USER_A))
    user_a.delegated_capital_usd = CAPITAL
    user_b = h_store.upsert_user(_user(USER_B))
    user_b.delegated_capital_usd = CAPITAL

    await sentinel_loop.tick_once(now=1_000)
    await helix_loop.tick_once(now=1_000)

    sentinel_targets: dict[str, int] = {}
    for call in s_onchain.pending:
        if call.method == "allocateToStrategy" and call.strategy is not None:
            sentinel_targets[call.strategy] = sentinel_targets.get(call.strategy, 0) + call.amount

    helix_targets: dict[str, int] = {}
    for call in h_onchain.pending:
        if call.method == "allocateToStrategy" and call.strategy is not None:
            helix_targets[call.strategy] = helix_targets.get(call.strategy, 0) + call.amount

    if not sentinel_targets:
        raise AssertionError("flow 1: Sentinel produced no allocations for User A")
    if not helix_targets:
        raise AssertionError("flow 2a: Helix produced no allocations for User B")

    # Materially different = ≥1 strategy in one set is not in the other,
    # OR weights differ by ≥5% on a shared strategy. The phase3-plan
    # defines the threshold; we keep the 5% number as-is.
    s_set = set(sentinel_targets)
    h_set = set(helix_targets)
    set_diff = s_set.symmetric_difference(h_set)
    weight_diff_threshold = 0.05 * CAPITAL
    weight_diffs = {
        sid: abs(sentinel_targets.get(sid, 0) - helix_targets.get(sid, 0)) for sid in s_set & h_set
    }
    max_weight_diff = max(weight_diffs.values()) if weight_diffs else 0
    if not set_diff and max_weight_diff < weight_diff_threshold:
        raise AssertionError(
            f"flow 2b: Sentinel and Helix produced effectively identical "
            f"allocations (set_diff={set_diff}, max_weight_diff="
            f"{max_weight_diff:.0f} < {weight_diff_threshold:.0f}). "
            f"Sentinel: {sentinel_targets}; Helix: {helix_targets}."
        )

    return {"sentinel": sentinel_targets, "helix": helix_targets}


# ─── flow 3: drawdown defund ───────────────────────────────


async def assert_drawdown_defund() -> str:
    """Set up User A holding a strategy whose NAV breaches the 20%
    drawdown threshold; assert Sentinel emits defund within one tick."""
    universe = _common_universe()
    loop, store, onchain = _build_loop(SentinelAllocator(), universe)

    sid = universe[0].strategy_id
    user = store.upsert_user(_user(USER_A, drawdown_bps=2_000))
    user.delegated_capital_usd = CAPITAL
    user.allocations[sid] = AllocationState(
        strategy_id=sid,
        chain_id=2368,
        declared_class="momentum_v1",
        capital_deployed_usd=10_000,
        high_water_mark_usd=10_000,
        nav_usd=7_500,  # -25% drawdown — past 20% threshold
    )
    user.last_rebalance_ts = 1_000  # suppress rebalance pass

    await loop.tick_once(now=1_100)

    defunds = [c for c in onchain.pending if c.method == "defundStrategy"]
    if len(defunds) != 1:
        raise AssertionError(f"flow 3: expected exactly 1 defundStrategy, got {len(defunds)}")
    if defunds[0].reason != "DRAWDOWN_BREACH":
        raise AssertionError(
            f"flow 3: defund reason is {defunds[0].reason!r}, expected DRAWDOWN_BREACH"
        )
    if not user.allocations[sid].defunded:
        raise AssertionError("flow 3: AllocationState.defunded was not flipped to True")
    strategy = defunds[0].strategy
    assert strategy is not None  # defund calls always carry a strategy
    return strategy


# ─── flow 4: HWM-cross fee settle ──────────────────────────


async def assert_fee_settle() -> str:
    """Set up User B holding a strategy whose NAV crosses HWM × 1.05;
    assert Helix emits settleStrategyFee within one tick."""
    universe = _common_universe()
    loop, store, onchain = _build_loop(HelixAllocator(), universe)

    sid = universe[1].strategy_id
    user = store.upsert_user(_user(USER_B))
    user.delegated_capital_usd = CAPITAL
    user.allocations[sid] = AllocationState(
        strategy_id=sid,
        chain_id=2368,
        declared_class="momentum_v1",
        capital_deployed_usd=10_000,
        high_water_mark_usd=10_000,
        nav_usd=10_600,  # +6% — past the 5% fee_threshold floor
    )
    user.last_rebalance_ts = 1_000  # suppress rebalance pass

    # Fee check fires only after `fee_check_interval_sec` since the loop
    # was constructed; force the gate by stretching the clock.
    await loop.tick_once(now=10_000)

    settles = [c for c in onchain.pending if c.method == "settleStrategyFee"]
    if len(settles) != 1:
        raise AssertionError(f"flow 4: expected exactly 1 settleStrategyFee, got {len(settles)}")
    if settles[0].strategy != sid:
        raise AssertionError(f"flow 4: fee settled on {settles[0].strategy}, expected {sid}")
    strategy = settles[0].strategy
    assert strategy is not None  # fee-settle calls always carry a strategy
    return strategy


# ─── orchestrator ─────────────────────────────────────────


async def main() -> int:
    failures: list[str] = []

    try:
        targets = await assert_divergence()
        s = targets["sentinel"]
        h = targets["helix"]
        print(f"[ok]   flow 1+2: divergence — Sentinel={dict(s)}; Helix={dict(h)}")
    except AssertionError as exc:
        print(f"[FAIL] flow 1+2: {exc}", file=sys.stderr)
        failures.append("flow 1+2")

    try:
        defunded = await assert_drawdown_defund()
        print(f"[ok]   flow 3:   drawdown defund — Sentinel defunded {defunded}")
    except AssertionError as exc:
        print(f"[FAIL] flow 3: {exc}", file=sys.stderr)
        failures.append("flow 3")

    try:
        settled = await assert_fee_settle()
        print(f"[ok]   flow 4:   HWM fee settle — Helix settled {settled}")
    except AssertionError as exc:
        print(f"[FAIL] flow 4: {exc}", file=sys.stderr)
        failures.append("flow 4")

    if failures:
        print(f"\n[FAIL] {len(failures)} acceptance flow(s) failed: {failures}", file=sys.stderr)
        return 1
    print("\n[ok]   all four Phase 3 acceptance flows passed.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
