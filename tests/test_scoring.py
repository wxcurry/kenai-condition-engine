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


def test_stale_data_lowers_confidence() -> None:
    fresh = score_conditions(
        ScoreInput(
            source_freshness_hours={"usgs": 2, "adfg_fish_counts": 10, "nws": 1},
        )
    )
    stale = score_conditions(
        ScoreInput(
            source_freshness_hours={"usgs": 30, "adfg_fish_counts": 60, "nws": 8},
        )
    )

    assert stale.confidence < fresh.confidence
    assert stale.source_freshness_status == "stale"


def test_missing_source_lowers_confidence() -> None:
    complete = score_conditions(
        ScoreInput(source_freshness_hours={"usgs": 2, "adfg_fish_counts": 10, "nws": 1})
    )
    missing = score_conditions(
        ScoreInput(
            source_freshness_hours={"usgs": 2},
            missing_sources=["adfg_fish_counts", "nws"],
        )
    )

    assert missing.confidence < complete.confidence
    assert "missing required source" in " ".join(missing.reasons).lower()


def test_good_water_and_weather_produces_higher_score() -> None:
    poor = score_conditions(
        ScoreInput(
            water_temperature_f=65,
            flow_percentile=92,
            recent_rain_inches_24h=0.9,
            wind_mph=22,
            barometric_trend="falling",
        )
    )
    good = score_conditions(
        ScoreInput(
            water_temperature_f=52,
            flow_percentile=55,
            recent_rain_inches_24h=0.05,
            wind_mph=6,
            barometric_trend="steady",
        )
    )

    assert good.overall_score > poor.overall_score
    assert good.overall_status == "excellent"


def test_dangerous_flow_or_flood_alert_lowers_score() -> None:
    normal = score_conditions(ScoreInput(flow_percentile=55))
    dangerous = score_conditions(
        ScoreInput(flow_percentile=99, flood_alert_active=True, flood_alert_severity="warning")
    )

    assert dangerous.overall_score < normal.overall_score
    assert dangerous.overall_status == "fair"
    assert any("flood" in reason.lower() for reason in dangerous.reasons)


def test_species_and_location_scores_are_reported() -> None:
    result = score_conditions(
        ScoreInput(
            species="sockeye",
            location="lower_kenai",
            fish_count_3day_avg=35_000,
            fish_count_trend="rising",
            tide_stage="incoming",
            water_temperature_f=52,
            flow_percentile=55,
        )
    )

    assert result.species_scores["sockeye"] > 75
    assert result.location_scores["lower_kenai"] > 70
    assert result.overall_score >= 75


def test_score_result_explains_change_confidence_legal_status_and_user_action() -> None:
    result = score_conditions(
        ScoreInput(
            water_temperature_f=65,
            flow_percentile=99,
            recent_rain_inches_24h=0.9,
            wind_mph=22,
            missing_sources=["baseline_regulations", "adfg_fish_counts"],
        )
    )

    assert result.score_delta_reason
    assert result.contributing_factors
    assert result.limiting_factors
    assert "missing" in result.confidence_explanation.lower()
    assert result.legal_explanation
    assert result.recommended_user_action
