from datetime import UTC, datetime, timedelta

from kenai_engine.fishing_conditions import (
    AccessConditionSignal,
    BiologicalSignal,
    DataFreshness,
    FishingConditionInput,
    HydrologySnapshot,
    TideSnapshot,
    WeatherSnapshot,
    extract_tide_snapshot,
    score_fishing_conditions,
    sockeye_run_context_for_date,
)
from kenai_engine.models import SourceHealth, TidePrediction

NOW = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)


def test_incoming_tide_improves_score_for_tide_relevant_access() -> None:
    incoming = _base_input(tide=TideSnapshot(phase="incoming", movement_strength=0.8))
    outgoing = _base_input(tide=TideSnapshot(phase="outgoing", movement_strength=0.8))

    assert score_fishing_conditions(incoming).score > score_fishing_conditions(outgoing).score


def test_slack_tide_reduces_lower_river_score() -> None:
    incoming = _base_input(tide=TideSnapshot(phase="incoming", movement_strength=0.8))
    slack = _base_input(tide=TideSnapshot(phase="slack_high", movement_strength=0.1))

    result = score_fishing_conditions(slack)

    assert result.score < score_fishing_conditions(incoming).score
    assert any("slack" in factor.explanation.lower() for factor in result.topNegativeFactors)


def test_flow_trend_affects_score_and_freshness_confidence_is_separate() -> None:
    stable = _base_input(
        hydrology=HydrologySnapshot(flow_percentile=55, flow_trend="stable", water_temp_f=52)
    )
    rising = _base_input(
        hydrology=HydrologySnapshot(flow_percentile=92, flow_trend="rising", water_temp_f=52),
        freshness=[DataFreshness(source="usgs", status="stale", age_hours=18)],
    )

    result = score_fishing_conditions(rising)

    assert result.score < score_fishing_conditions(stable).score
    assert result.confidence == "Low"
    assert result.rating in {"Poor", "Fair", "Good", "Excellent"}


def test_missing_tide_data_still_returns_cautious_result() -> None:
    result = score_fishing_conditions(
        FishingConditionInput(
            generated_at=NOW,
            target_species="sockeye",
            access_id="kenai_river_mouth",
            hydrology=HydrologySnapshot(flow_percentile=55, flow_trend="stable", water_temp_f=52),
            weather=WeatherSnapshot(wind_mph=8, precipitation_inches_24h=0.05),
            access=AccessConditionSignal(
                access_id="kenai_river_mouth",
                selected_access_id="kenai_river_mouth",
                tide_relevance="high",
                match_confidence=0.8,
            ),
        )
    )

    assert 0 <= result.score <= 100
    assert result.confidence in {"Low", "Medium"}
    assert any("missing" in factor.explanation.lower() for factor in result.topNegativeFactors)


def test_biological_timing_increases_score_without_guarantee_copy() -> None:
    result = score_fishing_conditions(
        _base_input(
            biological=BiologicalSignal(
                species="sockeye",
                run_phase="Peak",
                run_timing_percentile=0.85,
                fish_count_trend="improving",
                pulse_strength=0.65,
                seven_day_avg=95_000,
            )
        )
    )

    joined = " ".join(
        [
            result.officialSourceReminder,
            *[factor.explanation for factor in result.topPositiveFactors],
        ]
    ).lower()
    assert result.score >= 70
    assert "guarantee" not in joined
    assert "check official adf&g" in joined


def test_access_activity_applies_only_to_matching_access() -> None:
    matching = _base_input(
        access=AccessConditionSignal(
            access_id="kenai_river_mouth",
            selected_access_id="kenai_river_mouth",
            match_confidence=0.9,
        )
    )
    fallback = _base_input(
        access=AccessConditionSignal(
            access_id="soldotna",
            selected_access_id="kenai_river_mouth",
            match_confidence=0.2,
        )
    )

    assert score_fishing_conditions(matching).score > score_fishing_conditions(fallback).score


def test_regulation_copy_remains_source_check_only() -> None:
    result = score_fishing_conditions(
        _base_input(freshness=[DataFreshness(source="adfg_emergency_orders", status="cached")])
    )

    text = " ".join(
        [
            result.officialSourceReminder,
            result.dataFreshnessSummary,
            *[factor.explanation for factor in result.topNegativeFactors],
        ]
    ).lower()
    assert "legal" not in text
    assert "allowed" not in text
    assert "check official adf&g" in text


def test_malformed_and_missing_data_lower_confidence_without_crashing() -> None:
    result = score_fishing_conditions(
        FishingConditionInput(
            generated_at=NOW,
            target_species="sockeye",
            data_freshness=[
                DataFreshness(source="usgs", status="malformed"),
                DataFreshness(source="noaa_tides", status="missing"),
            ],
        )
    )

    assert result.confidence == "Low"
    assert 0 <= result.score <= 100
    assert "malformed" in result.dataFreshnessSummary


def test_extract_tide_snapshot_reports_phase_and_next_tides() -> None:
    tide = extract_tide_snapshot(
        [
            TidePrediction(
                predicted_at=NOW - timedelta(hours=3),
                height_ft=2,
                tide_type="L",
            ),
            TidePrediction(
                predicted_at=NOW + timedelta(hours=3),
                height_ft=20,
                tide_type="H",
            ),
        ],
        NOW,
        access_tide_relevance="high",
    )

    assert tide is not None
    assert tide.phase == "incoming"
    assert tide.height_delta_ft == 18
    assert tide.hours_until_high == 3


def test_source_health_extractor_marks_cached_adfg_as_not_current() -> None:
    result = score_fishing_conditions(
        _base_input(
            source_health=[
                SourceHealth(
                    source="adfg_emergency_orders",
                    status="degraded",
                    freshness_status="stale",
                    last_checked_at=NOW - timedelta(hours=30),
                    message="Using cached emergency order snapshot.",
                )
            ]
        )
    )

    assert result.confidence == "Low"
    assert "cached/stale" in result.dataFreshnessSummary


def test_sockeye_run_context_uses_seed_historical_data_without_live_claim() -> None:
    signal = sockeye_run_context_for_date(NOW.date())

    assert signal is not None
    assert signal.species == "sockeye"
    assert signal.run_phase == "Peak"
    assert signal.historical_only is True


def _base_input(
    *,
    hydrology: HydrologySnapshot | None = None,
    tide: TideSnapshot | None = None,
    weather: WeatherSnapshot | None = None,
    biological: BiologicalSignal | None = None,
    access: AccessConditionSignal | None = None,
    freshness: list[DataFreshness] | None = None,
    source_health: list[SourceHealth] | None = None,
) -> FishingConditionInput:
    return FishingConditionInput(
        generated_at=NOW,
        target_species="sockeye",
        access_id="kenai_river_mouth",
        hydrology=hydrology
        or HydrologySnapshot(flow_percentile=55, flow_trend="stable", water_temp_f=52),
        tide=tide if tide is not None else TideSnapshot(phase="incoming", movement_strength=0.7),
        weather=weather or WeatherSnapshot(wind_mph=8, precipitation_inches_24h=0.05),
        biological=biological
        or BiologicalSignal(
            species="sockeye",
            run_phase="Pre-Peak",
            run_timing_percentile=0.55,
            fish_count_trend="stable",
        ),
        access=access
        or AccessConditionSignal(
            access_id="kenai_river_mouth",
            selected_access_id="kenai_river_mouth",
            tide_relevance="high",
            match_confidence=0.8,
        ),
        data_freshness=freshness,
        source_health=source_health or [],
    )
