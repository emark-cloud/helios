"""HelixAllocator ranking + allocate math.

The §11.4 callout pins Helix-lite v1 to:

    Rank = ReputationScore × CapacityFactor × HelixFeeFactor × ClassFitFactor

with regime fixed at NORMAL. The bar for these tests is the same as
Sentinel's: the product collapses on any zeroed factor. The
*differentiator* — the continuous fee-fit penalty — gets its own
divergence test against Sentinel on a shared fixture.
"""

from __future__ import annotations

import inspect

from helios_allocator.helpers import correlation
from helios_allocator.helpers.regime import helix_fee_factor
from helios_allocator.types import MetaStrategy, Regime, StrategyCandidate
from helix.allocator import HelixAllocator
from sentinel.allocator import SentinelAllocator


def _meta(**overrides: object) -> MetaStrategy:
    base: dict[str, object] = dict(
        user_address="0x" + "ab" * 20,
        allowed_strategy_classes=("momentum_v1",),
        allowed_assets=("USDC", "WKITE", "WETH"),
        allowed_chains=(2368,),
        max_capital_usd=10_000,
        max_per_strategy_bps=10_000,
        max_strategies_count=3,
        drawdown_threshold_bps=1_500,
        max_fee_rate_bps=2_500,
        rebalance_cadence_sec=900,
        valid_until=2_000_000_000,
        bootstrap_share_bps=0,  # Helix-lite v1 has no bootstrap pool
    )
    base.update(overrides)
    return MetaStrategy(**base)  # type: ignore[arg-type]


def _candidate(
    sid: str,
    *,
    rep: float = 0.8,
    fee: int = 1_000,
    cls: str = "momentum_v1",
    capacity: int = 100_000,
    deployed: int = 0,
    stake: int = 5_000,
    trades_attested: int = 100,
) -> StrategyCandidate:
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


def test_score_uses_helix_fee_factor() -> None:
    a = HelixAllocator()
    user = _meta(max_fee_rate_bps=2_000)
    c = _candidate("0x" + "11" * 20, rep=1.0, fee=500, capacity=1_000, deployed=0)
    [score] = a.rank_strategies(user, [c])
    # rep=1, capacity=1, class_fit=1 → score = helix_fee_factor(500, 2000, NORMAL)
    expected = helix_fee_factor(500, 2_000, Regime.NORMAL)
    assert abs(score - expected) < 1e-9


def test_class_mismatch_zeroes_score() -> None:
    a = HelixAllocator()
    user = _meta()
    c = _candidate("0x" + "11" * 20, cls="yield_rotation_v1", rep=0.9)
    [score] = a.rank_strategies(user, [c])
    assert score == 0.0


def test_fee_above_max_zeroes_score() -> None:
    a = HelixAllocator()
    user = _meta(max_fee_rate_bps=500)
    c = _candidate("0x" + "11" * 20, fee=2_000)
    [score] = a.rank_strategies(user, [c])
    assert score == 0.0


def test_capacity_factor_proportional() -> None:
    a = HelixAllocator()
    user = _meta()
    c = _candidate("0x" + "11" * 20, rep=1.0, fee=0, capacity=10_000, deployed=7_500)
    [score] = a.rank_strategies(user, [c])
    # capacity=0.25; fee=0 → helix_fee_factor headroom=1.0 → NORMAL=1.0
    assert abs(score - 0.25) < 1e-9


def test_allocate_filters_zero_scored() -> None:
    a = HelixAllocator()
    user = _meta(max_strategies_count=3)
    good = _candidate("0x" + "11" * 20, rep=0.8)
    bad = _candidate("0x" + "22" * 20, cls="yield_rotation_v1", rep=0.9)
    targets = a.allocate(user, [good, bad], capital=10_000)
    assert len(targets) == 1
    assert targets[0].strategy_id == good.strategy_id


def test_allocate_caps_per_strategy_bps() -> None:
    a = HelixAllocator()
    user = _meta(max_per_strategy_bps=3_000, max_strategies_count=2)
    only = _candidate("0x" + "11" * 20, rep=1.0)
    [target] = a.allocate(user, [only], capital=10_000)
    assert target.capital_usd == 3_000
    assert target.weight_bps == 3_000


def test_diverges_from_sentinel_on_shared_fixture() -> None:
    """The whole point of Helix existing is to produce a *different*
    allocation than Sentinel on the same input. The fee-factor
    curvature is what provides that divergence — Helix's continuous
    penalty pulls capital toward cheaper strategies in NORMAL regime,
    while Sentinel's binary fee_fit treats them equally.

    If this test ever fails, the fee-factor curve no longer separates
    Helix from the reference baseline and the WS3.A acceptance bar
    ("allocator decisions visibly diverge") is broken. Tighten the
    curve OR seed the demo with strategies whose fees straddle the
    user's cap.
    """
    user = _meta(
        max_fee_rate_bps=2_500,
        max_per_strategy_bps=10_000,
        max_strategies_count=3,
    )
    candidates = [
        # Same reputation; the only difference is fee. Sentinel scores
        # both at rep × 1 × 1 × 1 → equal weights. Helix's fee_factor
        # ranks `cheap` higher than `pricey`.
        _candidate("0x" + "11" * 20, rep=0.8, fee=200, stake=5_000),
        _candidate("0x" + "22" * 20, rep=0.8, fee=2_000, stake=5_000),
        _candidate("0x" + "33" * 20, rep=0.8, fee=800, stake=5_000),
    ]
    sentinel_targets = {
        t.strategy_id: t.capital_usd
        for t in SentinelAllocator().allocate(user, list(candidates), capital=30_000)
    }
    helix_targets = {
        t.strategy_id: t.capital_usd
        for t in HelixAllocator().allocate(user, list(candidates), capital=30_000)
    }
    # Sentinel splits ~equally (binary fee_fit → identical scores).
    sentinel_spread = max(sentinel_targets.values()) - min(sentinel_targets.values())
    helix_spread = max(helix_targets.values()) - min(helix_targets.values())
    # Helix must produce a *larger* spread — the fee-factor differentiates.
    assert helix_spread > sentinel_spread, (
        f"Helix should spread allocation by fee. "
        f"sentinel_spread={sentinel_spread}, helix_spread={helix_spread}"
    )
    # And Helix must give the cheapest strategy more than the priciest.
    cheap, mid, pricey = "0x" + "11" * 20, "0x" + "33" * 20, "0x" + "22" * 20
    assert helix_targets[cheap] > helix_targets[mid] > helix_targets[pricey], helix_targets


def test_does_not_call_helix_greedy_pick_in_v1() -> None:
    """`Helios.md §11.4` callout: Helix-lite v1 ships without
    correlation-aware greedy. The helper is exposed in the SDK for
    third parties; Helix-v2 will adopt it. This test pins that v1
    boundary by importing the helper and asserting it's not on
    HelixAllocator's call graph (smoke test against accidental wiring)."""
    assert hasattr(correlation, "helix_greedy_pick")
    # If a future change wires greedy_pick into HelixAllocator, the
    # method body grows — this is a structural canary, not a behavioural
    # check. Tightening to AST inspection felt heavyweight for v1.
    src = inspect.getsource(HelixAllocator)
    assert "helix_greedy_pick" not in src, "Helix-v2 wiring leaked into v1"
