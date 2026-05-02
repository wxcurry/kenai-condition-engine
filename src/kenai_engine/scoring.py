"""Deterministic MVP scoring rules."""

from __future__ import annotations

from kenai_engine.models import ScoreInput, ScoreResult


def score_conditions(score_input: ScoreInput) -> ScoreResult:
    """Score conditions with regulatory overrides first."""

    reasons: list[str] = []

    if score_input.active_closure:
        reasons.append("Active closure overrides all other condition signals.")
        return ScoreResult(
            overall_score=0,
            overall_status="closed",
            confidence=score_input.confidence,
            reasons=reasons,
        )

    if score_input.active_restriction:
        reasons.append("Active restriction overrides baseline condition status.")
        return ScoreResult(
            overall_score=min(score_input.base_score, 45),
            overall_status="restricted",
            confidence=score_input.confidence,
            reasons=reasons,
        )

    if score_input.base_score >= 70:
        status = "good"
    elif score_input.base_score >= 40:
        status = "caution"
    else:
        status = "unknown"

    reasons.append("No active regulatory override found; using baseline placeholder score.")
    return ScoreResult(
        overall_score=score_input.base_score,
        overall_status=status,
        confidence=score_input.confidence,
        reasons=reasons,
    )
