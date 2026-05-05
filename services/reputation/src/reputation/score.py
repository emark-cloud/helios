"""Helios reputation §8.2 — full multi-component score formula.

Replaces the Phase 1 2-term proxy. For one strategy `s` of class `c`:

    ReputationScore = 0.40·PerformanceScore + 0.25·RiskScore
                    + 0.15·ProofScore + 0.10·StakeScore + 0.10·AgeScore

with cohort-relative `PerformanceScore` per `Helios.md §8.2`. Cohort statistics
(median + IQR per window) are computed by `reputation.cohort` from the
class-wide Sharpe distribution and passed in via `CohortContext`.

Sharpe input source (`Helios.md §8.2` deviation note). The spec says Sharpe is
"computed from realized trade P&L only, not unrealized mark-to-market". The
Phase 2 subgraph emits `Trade.amountIn` (no per-trade P&L) and
`NAVSnapshot.totalNAV` (mark-to-market). Until the strategy vault emits
per-trade realized P&L events, the engine uses NAV deltas as a proxy:
`annualized_sharpe_from_nav` resamples to daily buckets, computes log-returns,
and annualizes by `sqrt(365)`. This deviation is logged in
`docs/reputation-math.md` and revisited when WS3.A wires per-trade P&L.

`componentsHash` is `keccak256(abi.encode(int256, uint256, uint256, uint256, uint256))`
over the five components in fixed-point e4 form. WS3.A's `ReputationAnchor` v2
typehash adds this hash as a public field so the on-chain anchor records the
breakdown alongside the aggregate score.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

from eth_abi.abi import encode as abi_encode
from eth_utils.crypto import keccak

from reputation.cohort import CohortStats, normalize

# Aggregate weights (`Helios.md §8.2`). MUST sum to 1.0.
W_PERF = 0.40
W_RISK = 0.25
W_PROOF = 0.15
W_STAKE = 0.10
W_AGE = 0.10
# `math.isclose` rather than `==` because float sums can drift one ULP under
# future re-tuning. Currently the IEEE-754 sum is exact, so this is purely a
# hardening guard against silent invariant breaks. phase2-review.md item 17.
assert math.isclose(W_PERF + W_RISK + W_PROOF + W_STAKE + W_AGE, 1.0, abs_tol=1e-9)

# Performance window weights (sum to 1.0).
W_PERF_7D = 0.5
W_PERF_30D = 0.3
W_PERF_90D = 0.2

# Continuous-trading annualization (no weekend gap on Kite). 365 daily samples.
_TRADING_DAYS_PER_YEAR = 365

# Drawdown denominator from §8.2 RiskScore: 1 - clip(MaxDD90d / 5000, 0, 1).
_RISK_DD_DENOM_BPS = 5000


@dataclass(frozen=True, slots=True)
class WindowSharpe:
    """Per-window Sharpe (raw, pre-cohort-normalization)."""

    sharpe_7d: float
    sharpe_30d: float
    sharpe_90d: float


@dataclass(frozen=True, slots=True)
class CohortContext:
    """Cohort stats per window for the strategy's declared class."""

    win_7d: CohortStats
    win_30d: CohortStats
    win_90d: CohortStats


@dataclass(frozen=True, slots=True)
class ScoreInputs:
    sharpes: WindowSharpe
    max_drawdown_bps_90d: int
    valid_proofs: int
    total_proof_attempts: int
    stake_e18: int
    max_stake_in_class_e18: int
    trades_attested: int


@dataclass(frozen=True, slots=True)
class ScoreComponents:
    performance: float  # in [-1, 1] post-clip
    risk: float  # in [0, 1]
    proof: float  # in [0, 1]
    stake: float  # in [0, 1]
    age: float  # in [0, 1]


@dataclass(frozen=True, slots=True)
class PerformanceBreakdown:
    sharpe_7d: float
    sharpe_30d: float
    sharpe_90d: float
    norm_7d: float
    norm_30d: float
    norm_90d: float


@dataclass(frozen=True, slots=True)
class ScoreOutputs:
    score_e4: int  # signed int in [-10_000, +10_000] matching ReputationData.currentScore
    components: ScoreComponents
    components_hash: bytes  # 32 bytes
    perf_breakdown: PerformanceBreakdown


def compute_score(inputs: ScoreInputs, cohort: CohortContext) -> ScoreOutputs:
    stake = _stake(inputs.stake_e18, inputs.max_stake_in_class_e18)

    # WS7.B cold-start floor (`Helios.md §8.7`). With zero attested trades the
    # other four components have no signal yet — performance/risk/proof are
    # undefined and `_age` already collapses to 0. Returning `w_stake × stake`
    # gives a fresh strategy a non-zero, monotonic-in-stake floor that the
    # bootstrap pool can rank against, instead of forcing it to zero until the
    # first attested trade arrives. As proofs accumulate the full formula
    # takes over and the score is non-decreasing in expectation.
    if inputs.trades_attested <= 0:
        floor = W_STAKE * stake
        score_e4 = max(-10_000, min(10_000, round(10_000 * floor)))
        components = ScoreComponents(performance=0.0, risk=0.0, proof=0.0, stake=stake, age=0.0)
        zero_breakdown = PerformanceBreakdown(
            sharpe_7d=inputs.sharpes.sharpe_7d,
            sharpe_30d=inputs.sharpes.sharpe_30d,
            sharpe_90d=inputs.sharpes.sharpe_90d,
            norm_7d=0.0,
            norm_30d=0.0,
            norm_90d=0.0,
        )
        return ScoreOutputs(
            score_e4=score_e4,
            components=components,
            components_hash=hash_components(components),
            perf_breakdown=zero_breakdown,
        )

    perf, breakdown = _performance(inputs.sharpes, cohort)
    risk = _risk(inputs.max_drawdown_bps_90d)
    proof = _proof(inputs.valid_proofs, inputs.total_proof_attempts)
    age = _age(inputs.trades_attested)

    aggregate = W_PERF * perf + W_RISK * risk + W_PROOF * proof + W_STAKE * stake + W_AGE * age
    score_e4 = max(-10_000, min(10_000, round(10_000 * aggregate)))
    components = ScoreComponents(performance=perf, risk=risk, proof=proof, stake=stake, age=age)
    return ScoreOutputs(
        score_e4=score_e4,
        components=components,
        components_hash=hash_components(components),
        perf_breakdown=breakdown,
    )


def _performance(s: WindowSharpe, cohort: CohortContext) -> tuple[float, PerformanceBreakdown]:
    n7 = normalize(s.sharpe_7d, cohort.win_7d)
    n30 = normalize(s.sharpe_30d, cohort.win_30d)
    n90 = normalize(s.sharpe_90d, cohort.win_90d)
    raw = W_PERF_7D * n7 + W_PERF_30D * n30 + W_PERF_90D * n90
    perf = max(-1.0, min(1.0, raw))
    return perf, PerformanceBreakdown(
        sharpe_7d=s.sharpe_7d,
        sharpe_30d=s.sharpe_30d,
        sharpe_90d=s.sharpe_90d,
        norm_7d=n7,
        norm_30d=n30,
        norm_90d=n90,
    )


def _risk(max_dd_bps_90d: int) -> float:
    if max_dd_bps_90d <= 0:
        return 1.0
    return 1.0 - min(1.0, max_dd_bps_90d / _RISK_DD_DENOM_BPS)


def _proof(valid: int, attempts: int) -> float:
    if attempts <= 0:
        return 0.0
    return max(0.0, min(1.0, valid / attempts))


def _stake(stake_e18: int, max_stake_in_class_e18: int) -> float:
    if max_stake_in_class_e18 <= 0:
        return 0.0
    s = stake_e18 / 10**18
    m = max_stake_in_class_e18 / 10**18
    denom = math.log(1 + m / 1000)
    if denom <= 0:
        return 0.0
    return max(0.0, min(1.0, math.log(1 + s / 1000) / denom))


def _age(trades_attested: int) -> float:
    if trades_attested <= 0:
        return 0.0
    return min(1.0, math.sqrt(trades_attested / 1000))


def annualized_sharpe_from_nav(nav_series: Sequence[tuple[int, int]]) -> float:
    """Daily-resampled, log-return Sharpe annualized by sqrt(365).

    `nav_series` is `[(timestamp_unix, total_nav_e18), ...]` ascending. Returns
    0.0 when the window has fewer than 2 daily samples or zero stddev.

    Spec deviation: §8.2 calls for realized-trade-P&L Sharpe; Phase 2 uses NAV
    deltas as a proxy because the subgraph does not expose per-trade P&L. See
    module docstring + `docs/reputation-math.md`.
    """
    if len(nav_series) < 2:
        return 0.0
    # Resample to daily buckets — keep the latest NAV in each UTC day.
    daily: dict[int, int] = {}
    for ts, nav in nav_series:
        day = ts // 86_400
        daily[day] = nav
    series = [v for _, v in sorted(daily.items())]
    if len(series) < 2:
        return 0.0
    rets: list[float] = []
    for i in range(1, len(series)):
        prev, curr = series[i - 1], series[i]
        if prev <= 0 or curr <= 0:
            continue
        rets.append(math.log(curr / prev))
    if len(rets) < 2:
        return 0.0
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    if var <= 0:
        return 0.0
    return mean / math.sqrt(var) * math.sqrt(_TRADING_DAYS_PER_YEAR)


def hash_components(components: ScoreComponents) -> bytes:
    """`keccak256(abi.encode(int256, uint256, uint256, uint256, uint256))` over
    the five sub-scores in e4 fixed point. WS3.A's typehash v2 reconstructs
    the same hash on-chain so the anchor records the full breakdown.

    `performance` is the only component that can be negative (mapped to int256);
    risk/proof/stake/age are all in [0, 1] and stored as uint256.

    PR5 (phase2-review.md, perf list): the engine recomputes scores every tick
    even when the underlying components haven't changed. Hashing on the e4
    integer tuple gives us a hashable cache key with the same fidelity as the
    on-chain payload, so identical components reuse the prior keccak.
    """
    perf_e4 = round(components.performance * 10_000)
    risk_e4 = round(components.risk * 10_000)
    proof_e4 = round(components.proof * 10_000)
    stake_e4 = round(components.stake * 10_000)
    age_e4 = round(components.age * 10_000)
    return _hash_components_e4(perf_e4, risk_e4, proof_e4, stake_e4, age_e4)


@lru_cache(maxsize=4096)
def _hash_components_e4(
    perf_e4: int, risk_e4: int, proof_e4: int, stake_e4: int, age_e4: int
) -> bytes:
    payload = abi_encode(
        ["int256", "uint256", "uint256", "uint256", "uint256"],
        [perf_e4, risk_e4, proof_e4, stake_e4, age_e4],
    )
    return bytes(keccak(payload))


# ---- WS5.A: allocator reputation v1 -------------------------------------
#
# Four-component formula, weights documented in
# `docs/reputation-math.md §"Allocator reputation v1"`:
#
#     ReputationScore = 0.55·PnL + 0.20·Drawdown + 0.15·Retention + 0.10·Stake
#
# Cold-start floor mirrors §8.7: an allocator with zero users + zero
# breaches collapses to `w_stake · StakeScore`.

W_ALLOC_PNL = 0.55
W_ALLOC_DRAWDOWN = 0.20
W_ALLOC_RETENTION = 0.15
W_ALLOC_STAKE = 0.10
assert math.isclose(
    W_ALLOC_PNL + W_ALLOC_DRAWDOWN + W_ALLOC_RETENTION + W_ALLOC_STAKE, 1.0, abs_tol=1e-9
)


@dataclass(frozen=True, slots=True)
class AllocatorScoreInputs:
    aggregate_pnl_above_hwm_e18: int  # signed
    aggregate_capital_e18: int
    breach_total_count: int
    breach_response_count: int
    users_at_window_start: int
    users_at_window_end: int
    stake_e18: int
    max_stake_in_class_e18: int


@dataclass(frozen=True, slots=True)
class AllocatorScoreComponents:
    pnl: float  # in [-1, 1]
    drawdown: float  # in [0, 1]
    retention: float  # in [0, 1]
    stake: float  # in [0, 1]


@dataclass(frozen=True, slots=True)
class AllocatorScoreOutputs:
    score_e4: int
    components: AllocatorScoreComponents
    components_hash: bytes


def compute_allocator_score(inputs: AllocatorScoreInputs) -> AllocatorScoreOutputs:
    stake = _stake(inputs.stake_e18, inputs.max_stake_in_class_e18)

    # Cold-start floor: no users at either end of the retention window
    # AND no breaches recorded — nothing to score on. Stake is the only
    # legible signal, same posture as `Helios.md §8.7` for strategies.
    no_activity = (
        inputs.users_at_window_start <= 0
        and inputs.users_at_window_end <= 0
        and inputs.breach_total_count <= 0
    )
    if no_activity:
        floor = W_ALLOC_STAKE * stake
        score_e4 = max(-10_000, min(10_000, round(10_000 * floor)))
        components = AllocatorScoreComponents(pnl=0.0, drawdown=0.0, retention=0.0, stake=stake)
        return AllocatorScoreOutputs(
            score_e4=score_e4,
            components=components,
            components_hash=hash_allocator_components(components),
        )

    pnl = _allocator_pnl(inputs.aggregate_pnl_above_hwm_e18, inputs.aggregate_capital_e18)
    drawdown = _allocator_drawdown(inputs.breach_total_count, inputs.breach_response_count)
    retention = _allocator_retention(inputs.users_at_window_start, inputs.users_at_window_end)

    aggregate = (
        W_ALLOC_PNL * pnl
        + W_ALLOC_DRAWDOWN * drawdown
        + W_ALLOC_RETENTION * retention
        + W_ALLOC_STAKE * stake
    )
    score_e4 = max(-10_000, min(10_000, round(10_000 * aggregate)))
    components = AllocatorScoreComponents(
        pnl=pnl, drawdown=drawdown, retention=retention, stake=stake
    )
    return AllocatorScoreOutputs(
        score_e4=score_e4,
        components=components,
        components_hash=hash_allocator_components(components),
    )


def _allocator_pnl(pnl_e18: int, capital_e18: int) -> float:
    """Aggregate P&L above HWM, normalized by capital under management
    and clipped to [-1, 1]. Returns 0.0 when capital is zero (the
    cold-start branch handles the truly-empty case before we get here)."""
    if capital_e18 <= 0:
        return 0.0
    ratio = pnl_e18 / capital_e18
    return max(-1.0, min(1.0, ratio))


def _allocator_drawdown(total: int, responded: int) -> float:
    """Fraction of breaches defunded within `_DRAWDOWN_RESPONSE_SEC` of
    the breach. Returns 1.0 when no breaches occurred — an allocator with
    no triggers shouldn't be penalized; absence of evidence is rewarded.
    The breach feed is bounded to the 30d retention window upstream so
    a stale clean record can't carry indefinitely."""
    if total <= 0:
        return 1.0
    return max(0.0, min(1.0, responded / total))


def _allocator_retention(start: int, end: int) -> float:
    """Fraction of users present at window start who are still delegated
    at window end. Returns 1.0 when there were no users to retain — a
    fresh allocator with no starting cohort can't have churned anyone."""
    if start <= 0:
        return 1.0
    return max(0.0, min(1.0, end / start))


def hash_allocator_components(components: AllocatorScoreComponents) -> bytes:
    """`keccak256(abi.encode(int256, uint256, uint256, uint256))` over the
    four allocator sub-scores in e4 fixed point. Different layout from
    the strategy `hash_components` (4 fields vs 5) — the on-chain
    `componentsHash` field is opaque bytes32, so the off-chain layout
    can vary by actor type without a contract change."""
    pnl_e4 = round(components.pnl * 10_000)
    drawdown_e4 = round(components.drawdown * 10_000)
    retention_e4 = round(components.retention * 10_000)
    stake_e4 = round(components.stake * 10_000)
    return _hash_alloc_components_e4(pnl_e4, drawdown_e4, retention_e4, stake_e4)


@lru_cache(maxsize=4096)
def _hash_alloc_components_e4(
    pnl_e4: int, drawdown_e4: int, retention_e4: int, stake_e4: int
) -> bytes:
    payload = abi_encode(
        ["int256", "uint256", "uint256", "uint256"],
        [pnl_e4, drawdown_e4, retention_e4, stake_e4],
    )
    return bytes(keccak(payload))
