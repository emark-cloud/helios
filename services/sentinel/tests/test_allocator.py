"""SentinelAllocator ranking + allocate math.

Verifies the §8.3 product rule: rank = rep × capacity × fee × class.
A zero in any factor zeroes the rank — that's the point.
"""

from __future__ import annotations

from helios_allocator.types import AllocationTarget, MetaStrategy, StrategyCandidate
from sentinel.allocator import SentinelAllocator, diff_allocations


def _meta(**overrides: object) -> MetaStrategy:
    base: dict[str, object] = dict(
        user_address="0x" + "ab" * 20,
        allowed_strategy_classes=("momentum_v1",),
        allowed_assets=("USDC", "WKITE", "WETH"),
        allowed_chains=(2368,),
        max_capital_usd=10_000,
        max_per_strategy_bps=4_000,
        max_strategies_count=3,
        drawdown_threshold_bps=1_500,
        max_fee_rate_bps=2_500,
        rebalance_cadence_sec=900,
        valid_until=2_000_000_000,
    )
    base.update(overrides)
    return MetaStrategy(**base)  # type: ignore[arg-type]


def _candidate(
    sid: str = "0x" + "11" * 20,
    *,
    rep: float = 0.8,
    fee: int = 1_000,
    cls: str = "momentum_v1",
    capacity: int = 100_000,
    deployed: int = 0,
    stake: int = 5_000,
    trades_attested: int = 100,
) -> StrategyCandidate:
    # Default `trades_attested=100` keeps the main-pool baseline intact;
    # cold-start tests opt in by passing `trades_attested=0`.
    return StrategyCandidate(
        strategy_id=sid,
        declared_class=cls,
        chain_id=2368,
        operator="0x" + "cc" * 20,
        fee_rate_bps=fee,
        stake_amount_usd=stake,
        max_capacity_usd=capacity,
        current_allocations_usd=deployed,
        reputation_score=rep,
        trades_attested=trades_attested,
    )


def test_score_is_product_of_factors() -> None:
    a = SentinelAllocator()
    user = _meta()
    c = _candidate(rep=0.5, fee=500, capacity=1_000, deployed=0)
    [score] = a.rank_strategies(user, [c])
    # capacity factor = 1.0 (nothing deployed); fee_fit = 1; class_fit = 1
    assert score == 0.5


def test_class_mismatch_zeroes_score() -> None:
    a = SentinelAllocator()
    user = _meta()
    c = _candidate(cls="yield_rotation_v1", rep=0.9)
    [score] = a.rank_strategies(user, [c])
    assert score == 0.0


def test_fee_above_max_zeroes_score() -> None:
    a = SentinelAllocator()
    user = _meta(max_fee_rate_bps=500)
    c = _candidate(fee=2_000)
    [score] = a.rank_strategies(user, [c])
    assert score == 0.0


def test_capacity_factor_proportional() -> None:
    a = SentinelAllocator()
    user = _meta()
    c = _candidate(rep=1.0, capacity=10_000, deployed=7_500)
    [score] = a.rank_strategies(user, [c])
    # 1 - 7500/10000 = 0.25
    assert abs(score - 0.25) < 1e-9


def test_allocate_filters_zero_scored() -> None:
    a = SentinelAllocator()
    user = _meta(max_strategies_count=3)
    good = _candidate("0x" + "11" * 20, rep=0.8)
    bad = _candidate("0x" + "22" * 20, cls="yield_rotation_v1", rep=0.9)
    targets = a.allocate(user, [good, bad], capital=10_000)
    assert len(targets) == 1
    assert targets[0].strategy_id == good.strategy_id


def test_allocate_caps_per_strategy_bps() -> None:
    a = SentinelAllocator()
    user = _meta(max_per_strategy_bps=3_000, max_strategies_count=2)
    only = _candidate(rep=1.0)
    [target] = a.allocate(user, [only], capital=10_000)
    # Cap = 30% of capital = 3_000; without the cap it'd take 100%.
    assert target.capital_usd == 3_000
    assert target.weight_bps == 3_000


def test_allocate_split_two_strategies_score_weighted() -> None:
    a = SentinelAllocator()
    user = _meta(max_per_strategy_bps=10_000, max_strategies_count=2)
    s1 = _candidate("0x" + "11" * 20, rep=0.6)
    s2 = _candidate("0x" + "22" * 20, rep=0.4)
    targets = a.allocate(user, [s1, s2], capital=10_000)
    [t1, t2] = sorted(targets, key=lambda t: t.strategy_id)
    # Weights are proportional to score: 0.6 / (0.6+0.4) = 60%
    assert t1.capital_usd == 6_000
    assert t2.capital_usd == 4_000


# ── WS7.B reputation cold-start (Helios.md §8.7) ─────────────────


def test_bootstrap_pool_funds_cold_start_strategy_excluded_by_main_filter() -> None:
    # Cold-start strategy: zero attested trades AND zero reputation. Main
    # pool's rank product collapses to 0 (rep × … = 0) so it gets nothing
    # there. The bootstrap pool reserves 10% of capital for it anyway.
    a = SentinelAllocator()
    user = _meta(max_per_strategy_bps=10_000, max_strategies_count=2)
    warm = _candidate("0x" + "11" * 20, rep=0.8, trades_attested=200)
    cold = _candidate("0x" + "22" * 20, rep=0.0, trades_attested=0, stake=10_000)
    targets = {t.strategy_id: t for t in a.allocate(user, [warm, cold], capital=10_000)}
    assert cold.strategy_id in targets
    # 10% bootstrap of 10_000 = 1_000, fully claimed by the only cold candidate.
    assert targets[cold.strategy_id].capital_usd == 1_000
    # Warm strategy still wins the remaining 9_000 in the main pool.
    assert targets[warm.strategy_id].capital_usd == 9_000


def test_bootstrap_pool_stake_weighted_with_flat_perf_prior() -> None:
    # Two cold-start strategies, identical reputation (=0). Stake-weighted
    # split inside the bootstrap pool — main pool has nothing to allocate
    # because both candidates have zero rank product.
    a = SentinelAllocator()
    user = _meta(
        bootstrap_share_bps=10_000,  # 100% bootstrap to isolate the math
        max_per_strategy_bps=10_000,
        max_strategies_count=2,
    )
    big = _candidate("0x" + "11" * 20, rep=0.0, trades_attested=0, stake=8_000)
    small = _candidate("0x" + "22" * 20, rep=0.0, trades_attested=0, stake=2_000)
    targets = {t.strategy_id: t for t in a.allocate(user, [big, small], capital=10_000)}
    # 8_000 / (8_000 + 2_000) = 80% to big, 20% to small.
    assert targets[big.strategy_id].capital_usd == 8_000
    assert targets[small.strategy_id].capital_usd == 2_000


def test_bootstrap_pool_unused_falls_back_to_main() -> None:
    # All candidates are graduated (trades_attested >= min). Bootstrap pool
    # finds nothing, so its 10% rolls over and the warm strategy receives
    # the entire capital from the main pool.
    a = SentinelAllocator()
    user = _meta(max_per_strategy_bps=10_000, max_strategies_count=2)
    warm = _candidate("0x" + "11" * 20, rep=0.8, trades_attested=500)
    [t] = a.allocate(user, [warm], capital=10_000)
    assert t.capital_usd == 10_000


def test_bootstrap_eligibility_respects_class_and_fee_filters() -> None:
    # Cold-start strategy with the wrong class is NOT bootstrap-eligible —
    # the user's hard constraints (class, fee) still bind. Bootstrap budget
    # rolls back to the main pool.
    a = SentinelAllocator()
    user = _meta(max_per_strategy_bps=10_000, max_strategies_count=2)
    warm = _candidate("0x" + "11" * 20, rep=0.8, trades_attested=500)
    wrong_class = _candidate(
        "0x" + "22" * 20,
        rep=0.0,
        trades_attested=0,
        cls="yield_rotation_v1",
    )
    targets = {t.strategy_id: t for t in a.allocate(user, [warm, wrong_class], capital=10_000)}
    assert wrong_class.strategy_id not in targets
    assert targets[warm.strategy_id].capital_usd == 10_000


def test_bootstrap_share_bps_zero_disables_pool() -> None:
    a = SentinelAllocator()
    user = _meta(
        bootstrap_share_bps=0,
        max_per_strategy_bps=10_000,
        max_strategies_count=2,
    )
    warm = _candidate("0x" + "11" * 20, rep=0.8, trades_attested=500)
    cold = _candidate("0x" + "22" * 20, rep=0.0, trades_attested=0)
    targets = {t.strategy_id: t for t in a.allocate(user, [warm, cold], capital=10_000)}
    # Without a bootstrap pool, the cold-start strategy gets nothing.
    assert cold.strategy_id not in targets
    assert targets[warm.strategy_id].capital_usd == 10_000


def test_per_strategy_cap_applies_after_pool_merge() -> None:
    # A strategy that is bootstrap-eligible AND wins the main pool should
    # not exceed `max_per_strategy_bps` after the pools are merged.
    a = SentinelAllocator()
    user = _meta(
        bootstrap_share_bps=10_000,  # 100% bootstrap
        max_per_strategy_bps=4_000,
        max_strategies_count=2,
    )
    only = _candidate("0x" + "11" * 20, rep=0.0, trades_attested=0, stake=10_000)
    [t] = a.allocate(user, [only], capital=10_000)
    # Cap enforced even when the bootstrap pool would happily allocate 100%.
    assert t.capital_usd == 4_000


def test_diff_allocations_emits_signed_deltas() -> None:
    current = {"0x" + "11" * 20: 5_000, "0x" + "22" * 20: 3_000}
    target = [
        AllocationTarget(
            strategy_id="0x" + "11" * 20, chain_id=2368, capital_usd=7_000, weight_bps=7_000
        ),
        AllocationTarget(
            strategy_id="0x" + "33" * 20, chain_id=2368, capital_usd=3_000, weight_bps=3_000
        ),
    ]
    ops = dict(diff_allocations(current, target))
    assert ops["0x" + "11" * 20] == 2_000  # increase
    assert ops["0x" + "22" * 20] == -3_000  # full removal
    assert ops["0x" + "33" * 20] == 3_000  # new
