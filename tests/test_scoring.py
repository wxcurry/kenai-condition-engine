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


def test_salmon_heat_stress_threshold_strongly_lowers_score() -> None:
    result = score_conditions(ScoreInput(water_temperature_f=65))

    assert result.overall_score == 48
    assert any("heat-stress" in reason.lower() for reason in result.reasons)


def test_heavy_rain_and_strong_wind_have_tiered_penalties() -> None:
    rough = score_conditions(
        ScoreInput(
            recent_rain_inches_24h=1.4,
            wind_mph=31,
        )
    )
    calm = score_conditions(
        ScoreInput(
            recent_rain_inches_24h=0.08,
            wind_mph=7,
        )
    )

    assert rough.overall_score == 40
    assert calm.overall_score == 78
    assert any("heavy rain" in reason.lower() for reason in rough.reasons)
    assert any("strong wind" in reason.lower() for reason in rough.reasons)


def test_air_temperature_and_rain_probability_affect_practical_conditions() -> None:
    cold_wet = score_conditions(
        ScoreInput(
            air_temperature_f=20,
            precipitation_probability=80,
        )
    )
    mild_dry = score_conditions(
        ScoreInput(
            air_temperature_f=55,
            precipitation_probability=20,
        )
    )

    assert cold_wet.overall_score == 62
    assert mild_dry.overall_score == 74
    assert any("cold air" in reason.lower() for reason in cold_wet.reasons)
    assert any("high rain probability" in reason.lower() for reason in cold_wet.reasons)


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


def test_chinook_count_signal_uses_lower_volume_thresholds() -> None:
    result = score_conditions(
        ScoreInput(
            species="chinook",
            fish_count_3day_avg_by_species={"chinook": 125},
            fish_count_trend_by_species={"chinook": "rising"},
        )
    )

    assert result.species_scores["chinook"] > result.species_scores["sockeye"]


def test_location_fish_count_adjustment_nudges_selected_location() -> None:
    result = score_conditions(
        ScoreInput(
            location="lower_kenai",
            fish_count_location_adjustments={"lower_kenai": 6},
        )
    )

    assert result.location_scores["lower_kenai"] > result.location_scores["upper_kenai"]


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
