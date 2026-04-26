"""Phase 1 score formula.

`Helios.md §8.2` defines the full multi-factor score. Phase 1 ships a
deliberately reduced version so the data path (subgraph → engine → anchor)
can be exercised end-to-end while the additional inputs (drawdown, capacity,
fee paid, sharpe-like volatility term) are wired up across surfaces:

    score_e4 = round(10_000 × (
        0.7 × clip(realized_pnl_30d / notional, -1, 1)
      + 0.3 × proof_validity_rate
    ))

Output is an int in [-10_000, +10_000] matching `ReputationData.currentScore`'s
on-chain unit.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScoreInputs:
    realized_pnl_30d_e18: int
    notional_e18: int  # capital deployed; 0 means strategy has no live allocation
    proof_validity_rate_bps: int  # 0..10_000


@dataclass(frozen=True, slots=True)
class ScoreOutputs:
    score_e4: int  # signed int in [-10_000, +10_000]
    pnl_term_e4: int
    proof_term_e4: int


def compute_phase1_score(inputs: ScoreInputs) -> ScoreOutputs:
    if inputs.notional_e18 <= 0:
        # No active allocation → P&L term is undefined. The cleanest semantics
        # is to drop the P&L weight and keep the proof-validity term, so a
        # newly registered strategy starts at +0.3 × proof_validity (typically
        # +3000 since all attested trades carry a valid proof).
        pnl_term_e4 = 0
    else:
        # ratio in fixed-point; clip to [-1.0, 1.0] expressed in 1e18 scale.
        ratio_e18 = (inputs.realized_pnl_30d_e18 * 10**18) // inputs.notional_e18
        clipped_e18 = max(-(10**18), min(10**18, ratio_e18))
        pnl_term_e4 = (clipped_e18 * 7000) // (10**18)  # 0.7 weight in e4

    proof_clipped = max(0, min(10_000, inputs.proof_validity_rate_bps))
    proof_term_e4 = (proof_clipped * 3000) // 10_000  # 0.3 weight in e4

    score = pnl_term_e4 + proof_term_e4
    score = max(-10_000, min(10_000, score))
    return ScoreOutputs(score_e4=score, pnl_term_e4=pnl_term_e4, proof_term_e4=proof_term_e4)
