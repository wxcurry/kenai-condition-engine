from kenai_engine.models import ScoreInput
from kenai_engine.scoring import score_conditions


def test_active_closure_forces_closed_status() -> None:
    result = score_conditions(
        ScoreInput(base_score=95, active_closure=True, active_restriction=True)
    )

    assert result.overall_status == "closed"
    assert result.overall_score == 0


def test_active_restriction_forces_restricted_status() -> None:
    result = score_conditions(ScoreInput(base_score=95, active_restriction=True))

    assert result.overall_status == "restricted"
    assert result.overall_score == 45


def test_baseline_score_maps_to_good_without_regulatory_override() -> None:
    result = score_conditions(ScoreInput(base_score=72))

    assert result.overall_status == "good"
    assert result.overall_score == 72
