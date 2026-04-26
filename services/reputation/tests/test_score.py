"""Phase 1 score formula. Bounds + clipping behavior."""

from __future__ import annotations

from reputation.score import ScoreInputs, compute_phase1_score


def test_zero_pnl_only_proof_validity() -> None:
    out = compute_phase1_score(
        ScoreInputs(realized_pnl_30d_e18=0, notional_e18=10**18, proof_validity_rate_bps=10_000)
    )
    # 0.7 × 0 + 0.3 × 1.0 = 0.3 → 3000 in e4
    assert out.score_e4 == 3000
    assert out.pnl_term_e4 == 0
    assert out.proof_term_e4 == 3000


def test_positive_pnl_full_proof_validity() -> None:
    # +50% return → 0.7 × 0.5 + 0.3 × 1.0 = 0.65 → 6500
    out = compute_phase1_score(
        ScoreInputs(
            realized_pnl_30d_e18=5 * 10**17,
            notional_e18=10**18,
            proof_validity_rate_bps=10_000,
        )
    )
    assert out.score_e4 == 6500


def test_negative_pnl_clips_at_minus_one() -> None:
    out = compute_phase1_score(
        ScoreInputs(
            realized_pnl_30d_e18=-5 * 10**18,  # -500% return
            notional_e18=10**18,
            proof_validity_rate_bps=10_000,
        )
    )
    # 0.7 × clip(-5, -1, 1) + 0.3 × 1 = -0.7 + 0.3 = -0.4 → -4000
    assert out.score_e4 == -4000


def test_positive_pnl_clips_at_plus_one() -> None:
    out = compute_phase1_score(
        ScoreInputs(
            realized_pnl_30d_e18=10 * 10**18,
            notional_e18=10**18,
            proof_validity_rate_bps=10_000,
        )
    )
    # 0.7 × 1 + 0.3 × 1 = 1.0 → 10_000
    assert out.score_e4 == 10_000


def test_no_notional_zeroes_pnl_term() -> None:
    out = compute_phase1_score(
        ScoreInputs(realized_pnl_30d_e18=10**18, notional_e18=0, proof_validity_rate_bps=10_000)
    )
    assert out.pnl_term_e4 == 0
    assert out.proof_term_e4 == 3000
    assert out.score_e4 == 3000


def test_score_bounded_by_int_e4_range() -> None:
    out = compute_phase1_score(
        ScoreInputs(
            realized_pnl_30d_e18=10**30, notional_e18=10**18, proof_validity_rate_bps=20_000
        )
    )
    assert -10_000 <= out.score_e4 <= 10_000
