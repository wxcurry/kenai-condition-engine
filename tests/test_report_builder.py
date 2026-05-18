from datetime import UTC, datetime
from pathlib import Path

from kenai_engine.models import (
    Alert,
    BaselineRegulation,
    FishCount,
    Regulation,
    Report,
    SourceHealth,
    TidePrediction,
    UsgsFlowStatistic,
    UsgsObservation,
    WeatherObservation,
)
from kenai_engine.report_builder import (
    build_condition_report,
    build_placeholder_report,
    write_latest_report,
)
from kenai_engine.sources.usgs import parse_usgs_payload


def test_condition_report_has_app_contract_shape() -> None:
    report = build_condition_report(datetime(2026, 5, 2, 12, 0, tzinfo=UTC))

    dumped = report.model_dump(mode="json")

    assert set(dumped) == {
        "schema_version",
        "engine_version",
        "generated_by",
        "report_date",
        "generated_at",
        "expires_at",
        "report_status",
        "river",
        "overall_score",
        "overall_status",
        "confidence",
        "confidence_band",
        "summary",
        "locations",
        "species_scores",
        "baseline_regulations",
        "emergency_orders",
        "regulations",
        "fish_counts",
        "alerts",
        "warnings",
        "source_health",
    }
    assert dumped["schema_version"] == "1.0.0"
    assert dumped["engine_version"] == "0.1.0"
    assert dumped["generated_by"] == "kenai-condition-engine"
    assert dumped["generated_at"] == "05-02-2026"
    assert dumped["expires_at"] == "2026-05-02T18:00:00Z"
    assert dumped["report_status"] == "degraded"
    assert dumped["confidence_band"] in {"low", "medium", "high"}
    assert dumped["river"] == "Kenai River"
    assert dumped["source_health"]
    assert all("freshness_status" in health for health in dumped["source_health"])


def test_default_source_health_exposes_adfg_fishing_reports_separately() -> None:
    generated_at = datetime(2026, 5, 16, 12, 0, tzinfo=UTC)

    report = build_condition_report(
        generated_at,
        alerts=[
            Alert(
                title="Northern Kenai Fishing Report",
                severity="info",
                summary="Early-run Kenai narrative is available.",
                source="adfg_fishing_reports",
            ),
            Alert(
                title="Flood Watch",
                severity="watch",
                summary="NWS alert is available.",
                source="NWS Anchorage",
            ),
        ],
    )

    health_by_source = {health.source: health for health in report.source_health}
    assert health_by_source["adfg_fishing_reports"].status == "ok"
    assert health_by_source["adfg_fishing_reports"].user_title == "Fishing report data current"
    assert health_by_source["adfg_fishing_reports"].freshness_status == "current"
    assert health_by_source["adfg_fishing_reports"].affects_score is False
    assert health_by_source["nws"].status == "ok"


def test_report_alerts_include_advisory_explanation_and_fishing_impact() -> None:
    report = build_condition_report(
        datetime(2026, 7, 22, 22, 0, tzinfo=UTC),
        regulations=[],
        fish_counts=[],
        alerts=[
            Alert(
                title="Flood Watch",
                severity="watch",
                summary="Flooding is possible on streams and rivers near Kenai.",
                source="NWS Anchorage",
            )
        ],
    )

    alert = report.model_dump(mode="json")["alerts"][0]

    assert alert["advisory_explanation"] == (
        "A flood watch means conditions could develop that raise river levels or "
        "create unsafe water conditions."
    )
    assert alert["fishing_impact"] == (
        "Higher or rising water can reduce bank access, make wading unsafe, move fish "
        "out of normal holding water, lower clarity, and make boat control harder."
    )


def test_report_alert_generic_fishing_impact_handles_empty_summary() -> None:
    report = build_condition_report(
        datetime(2026, 7, 22, 22, 0, tzinfo=UTC),
        regulations=[],
        fish_counts=[],
        alerts=[
            Alert(
                title="Special Weather Statement",
                severity="info",
                summary="",
                source="nws",
            )
        ],
    )

    alert = report.model_dump(mode="json")["alerts"][0]

    assert alert["fishing_impact"] == (
        "Special Weather Statement may affect access, safety, fish behavior, and the "
        "practicality of fishing before heading out."
    )
    assert not alert["fishing_impact"].startswith(" ")


def test_adfg_fishing_report_source_health_exposes_stale_and_failed_states() -> None:
    generated_at = datetime(2026, 5, 16, 12, 0, tzinfo=UTC)

    stale_report = build_condition_report(
        generated_at,
        regulations=[],
        fish_counts=[],
        alerts=[],
        source_health=[
            SourceHealth(
                source="adfg_fishing_reports",
                status="ok",
                last_checked_at=datetime(2026, 5, 15, 11, 59, tzinfo=UTC),
                message="Fetched ADF&G fishing reports.",
            )
        ],
    )
    failed_report = build_condition_report(
        generated_at,
        regulations=[],
        fish_counts=[],
        alerts=[],
        source_health=[
            SourceHealth(
                source="adfg_fishing_reports",
                status="failed",
                last_checked_at=generated_at,
                message="ADF&G fishing report fetch timed out.",
                last_error="ADF&G fishing report fetch timed out.",
            )
        ],
    )

    stale_source = stale_report.source_health[0]
    failed_source = failed_report.source_health[0]
    assert stale_source.status == "degraded"
    assert stale_source.freshness_status == "stale"
    assert stale_source.user_title == "Fishing report data needs attention"
    assert failed_source.status == "failed"
    assert failed_source.freshness_status == "missing"
    assert failed_source.user_title == "Fishing report data unavailable"
    assert failed_source.last_error == "ADF&G fishing report fetch timed out."


def test_condition_report_uses_production_copy() -> None:
    report = build_condition_report(
        datetime(2026, 5, 2, 12, 0, tzinfo=UTC),
        regulations=[],
        fish_counts=[],
        alerts=[],
    )

    combined_text = " ".join(
        [
            report.summary,
            *[alert.summary for alert in report.alerts],
            *[health.message for health in report.source_health],
        ]
    ).lower()

    banned_copy = [
        "mvp",
        "place" + "holder",
        "skele" + "ton",
        "production source " + "fetching is not " + "implemented",
    ]
    assert all(copy not in combined_text for copy in banned_copy)
    assert "condition report" in report.summary.lower()


def test_placeholder_report_alias_preserves_existing_import_contract() -> None:
    assert build_placeholder_report is build_condition_report


def test_report_schema_version_is_required() -> None:
    payload = build_condition_report(datetime(2026, 5, 2, 12, 0, tzinfo=UTC)).model_dump(
        mode="json"
    )
    del payload["schema_version"]

    try:
        Report.model_validate(payload)
    except Exception as error:
        assert "schema_version" in str(error)
    else:
        raise AssertionError("Report validation should require schema_version.")


def test_report_generated_at_date_only_format_round_trips() -> None:
    payload = build_condition_report(datetime(2026, 5, 2, 12, 0, tzinfo=UTC)).model_dump(
        mode="json"
    )

    assert payload["generated_at"] == "05-02-2026"
    assert Report.model_validate(payload).generated_at == datetime(2026, 5, 2, tzinfo=UTC)


def test_write_latest_report_creates_json_file(tmp_path) -> None:
    path = write_latest_report(tmp_path)

    assert path.name == "latest.json"
    assert path.exists()


def test_report_includes_all_default_locations_when_data_is_missing() -> None:
    report = build_condition_report(datetime(2026, 5, 2, 12, 0, tzinfo=UTC))

    assert [location.id for location in report.locations] == [
        "cooper_landing_upper_kenai",
        "russian_river_confluence",
        "middle_kenai_skilak_outlet",
        "soldotna",
        "lower_kenai_tidewater",
        "kenai_river_mouth",
    ]
    assert all(location.confidence < report.confidence for location in report.locations)
    assert report.locations[0].water["monitoring_location_id"] == "USGS-15258000"
    assert report.locations[0].water["nwis_site_id"] == "15258000"
    assert report.locations[0].water["discharge_cfs"] is None
    assert report.locations[0].water["trend"] == "unknown"


def test_location_contract_includes_water_weather_and_explanation_fields() -> None:
    report = build_condition_report(datetime(2026, 5, 2, 12, 0, tzinfo=UTC))
    location = report.model_dump(mode="json")["locations"][0]

    assert location["status"] in {
        "poor",
        "fair",
        "good",
        "excellent",
        "restricted",
        "closed",
        "unknown",
    }
    assert set(location["water"]) >= {
        "monitoring_location_id",
        "nwis_site_id",
        "discharge_cfs",
        "gage_height_ft",
        "water_temp_c",
        "water_temp_f",
        "turbidity_fnu",
        "specific_conductance_us_cm",
        "dissolved_oxygen_mg_l",
        "ph",
        "trend",
        "observed_at",
        "source",
    }
    assert set(location) >= {
        "bank_fishing_score",
        "boat_fishing_score",
        "sockeye_score",
        "chinook_score",
        "coho_score",
        "rainbow_trout_score",
        "dolly_varden_score",
        "score_delta_reason",
        "contributing_factors",
        "limiting_factors",
        "confidence_explanation",
        "legal_explanation",
        "recommended_user_action",
    }


def test_location_weather_includes_pulse_display_fields() -> None:
    generated_at = datetime(2026, 7, 22, 22, 0, tzinfo=UTC)
    report = build_condition_report(
        generated_at,
        usgs_observations=[
            UsgsObservation(
                site_id="15266300",
                monitoring_location_id="USGS-15266300",
                site_name="KENAI RIVER AT SOLDOTNA AK",
                parameter_code="00060",
                parameter_name="Discharge",
                value=5400,
                unit="ft3/s",
                observed_at=generated_at,
            ),
            UsgsObservation(
                site_id="15266300",
                monitoring_location_id="USGS-15266300",
                site_name="KENAI RIVER AT SOLDOTNA AK",
                parameter_code="63680",
                parameter_name="Turbidity",
                value=4.2,
                unit="FNU",
                observed_at=generated_at,
            ),
        ],
        regulations=[],
        fish_counts=[],
        alerts=[],
        weather_observations=[
            WeatherObservation(
                location="Kenai,AK",
                observed_at=generated_at,
                recent_rain_inches_24h=0.12,
                wind_mph=14,
                wind_direction="S",
                temperature_f=54,
                short_forecast="Light rain",
                precipitation_probability=60,
                detailed_forecast="Rain likely before midnight.",
                source="nws",
            )
        ],
    )

    soldotna = next(location for location in report.locations if location.id == "soldotna")

    assert soldotna.weather["weather_summary"] == "Light rain"
    assert soldotna.weather["wind"] == "14 mph S"
    assert soldotna.weather["rain_chance"] == "60%"
    assert soldotna.weather["clarity"] == "clear"
    assert soldotna.weather["clarity_source"] == "measured_turbidity"


def test_report_species_scores_are_supported_or_unknown_with_explanation() -> None:
    report = build_condition_report(datetime(2026, 5, 2, 12, 0, tzinfo=UTC))

    dumped = report.model_dump(mode="json")

    assert dumped["species_scores"]
    assert all(
        "species" in item and "status" in item and "explanation" in item
        for item in dumped["species_scores"]
    )


def test_baseline_regulation_appears_in_report() -> None:
    baseline = BaselineRegulation(
        id="sockeye-manual-review",
        species="sockeye",
        segments=["upper"],
        season_start="06-11",
        season_end="08-20",
        gear_notes="Artificial fly or lure unless official regulations say otherwise.",
        bag_possession_summary="Manual review required before relying on this summary.",
        source_url="https://www.adfg.alaska.gov/",
        notes="Production baseline regulation context.",
        last_reviewed=datetime(2026, 5, 1, tzinfo=UTC).date(),
    )

    report = build_condition_report(
        datetime(2026, 6, 20, 12, 0, tzinfo=UTC),
        regulations=[],
        fish_counts=[],
        alerts=[],
        baseline_regulations=[baseline],
    )

    assert report.baseline_regulations == [baseline]
    assert report.warnings == []


def test_missing_baseline_regulation_creates_warning_and_lowers_confidence() -> None:
    report = build_condition_report(
        datetime(2026, 6, 20, 12, 0, tzinfo=UTC),
        regulations=[],
        fish_counts=[],
        alerts=[],
        baseline_regulations=[],
    )

    assert any(warning.source == "baseline_regulations" for warning in report.warnings)
    assert report.confidence < 0.35


def test_explicit_empty_inputs_do_not_insert_default_records() -> None:
    report = build_condition_report(
        datetime(2026, 5, 2, 12, 0, tzinfo=UTC),
        regulations=[],
        fish_counts=[],
        alerts=[],
    )

    assert report.regulations == []
    assert report.fish_counts == []
    assert report.alerts == []
    assert _source_health_message(report, "adfg_emergency_orders") == (
        "0 normalized ADFG emergency orders available."
    )
    assert _source_health_message(report, "adfg_fish_counts") == (
        "ADF&G fish count source is outside its active run window."
    )
    assert _source_health_message(report, "nws") == "0 normalized NWS alerts available."


def test_real_closed_regulation_overrides_default_status() -> None:
    report = build_condition_report(
        datetime(2026, 5, 2, 12, 0, tzinfo=UTC),
        regulations=[
            Regulation(
                title="Kenai River closure",
                status="closed",
                effective_date=datetime(2026, 5, 2, tzinfo=UTC).date(),
                source_url="https://www.adfg.alaska.gov/",
                summary="Emergency order closes the fishery.",
            )
        ],
        fish_counts=[],
        alerts=[],
    )

    assert report.overall_status == "closed"
    assert report.overall_score == 0
    assert report.emergency_orders[0].status == "closed"
    assert report.summary == (
        "Active emergency order indicates a closure. Check official ADFG sources."
    )


def test_real_restricted_regulation_overrides_default_status() -> None:
    report = build_condition_report(
        datetime(2026, 5, 2, 12, 0, tzinfo=UTC),
        regulations=[
            Regulation(
                title="Kenai River restriction",
                status="restricted",
                effective_date=datetime(2026, 5, 2, tzinfo=UTC).date(),
                source_url="https://www.adfg.alaska.gov/",
                summary="Emergency order restricts the fishery.",
            )
        ],
        fish_counts=[],
        alerts=[],
    )

    assert report.overall_status == "restricted"
    assert report.overall_score == 45
    assert report.emergency_orders[0].status == "restricted"
    assert report.summary == (
        "Active emergency order indicates restrictions. Check official ADFG sources."
    )


def test_report_summary_warns_when_required_sources_are_missing() -> None:
    generated_at = datetime(2026, 7, 22, 22, 0, tzinfo=UTC)

    report = build_condition_report(
        generated_at,
        regulations=[],
        fish_counts=[],
        alerts=[],
        source_health=[
            SourceHealth(
                source="usgs",
                status="ok",
                last_checked_at=generated_at,
                message="Fetched USGS.",
            )
        ],
    )

    assert report.summary.startswith("Source warning: missing required sources")
    assert "adfg_emergency_orders" in report.summary
    assert any(warning.source == "adfg_emergency_orders" for warning in report.warnings)


def test_report_does_not_require_inactive_seasonal_fish_counts() -> None:
    generated_at = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)

    report = build_condition_report(
        generated_at,
        regulations=[],
        fish_counts=[],
        alerts=[],
        source_health=[
            SourceHealth(
                source="usgs",
                status="ok",
                last_checked_at=generated_at,
                message="Fetched USGS.",
            ),
            SourceHealth(
                source="usgs_statistics",
                status="ok",
                last_checked_at=generated_at,
                message="Fetched USGS statistics.",
            ),
            SourceHealth(
                source="adfg_emergency_orders",
                status="ok",
                last_checked_at=generated_at,
                message="Fetched ADF&G emergency orders.",
            ),
            SourceHealth(
                source="nws",
                status="ok",
                last_checked_at=generated_at,
                message="Fetched NWS.",
            ),
            SourceHealth(
                source="noaa_tides",
                status="ok",
                last_checked_at=generated_at,
                message="Fetched NOAA tides.",
            ),
        ],
    )

    assert "adfg_fish_counts" not in report.summary
    assert not any(warning.source == "adfg_fish_counts" for warning in report.warnings)
    assert "adfg_fish_counts" not in report.locations[0].confidence_explanation


def test_report_summary_warns_when_required_sources_are_stale() -> None:
    generated_at = datetime(2026, 7, 22, 22, 0, tzinfo=UTC)
    stale_time = datetime(2026, 7, 20, 22, 0, tzinfo=UTC)

    report = build_condition_report(
        generated_at,
        regulations=[],
        fish_counts=[],
        alerts=[],
        source_health=[
            SourceHealth(
                source="usgs",
                status="ok",
                last_checked_at=generated_at,
                message="Fetched USGS.",
            ),
            SourceHealth(
                source="usgs_statistics",
                status="ok",
                last_checked_at=generated_at,
                message="Fetched USGS statistics.",
            ),
            SourceHealth(
                source="adfg_emergency_orders",
                status="ok",
                last_checked_at=stale_time,
                message="Fetched ADF&G emergency orders.",
            ),
            SourceHealth(
                source="adfg_fish_counts",
                status="ok",
                last_checked_at=generated_at,
                message="Fetched ADF&G fish counts.",
            ),
            SourceHealth(
                source="nws",
                status="ok",
                last_checked_at=generated_at,
                message="Fetched NWS.",
            ),
            SourceHealth(
                source="noaa_tides",
                status="ok",
                last_checked_at=generated_at,
                message="Fetched NOAA tides.",
            ),
        ],
    )

    assert report.summary.startswith("Source warning: stale required sources")
    assert "adfg_emergency_orders" in report.summary
    assert any(
        warning.source == "adfg_emergency_orders" and warning.severity == "warning"
        for warning in report.warnings
    )


def test_failed_source_health_maps_to_user_visible_fields() -> None:
    generated_at = datetime(2026, 7, 22, 22, 0, tzinfo=UTC)

    report = build_condition_report(
        generated_at,
        regulations=[],
        fish_counts=[],
        alerts=[],
        source_health=[
            SourceHealth(
                source="adfg_emergency_orders",
                status="failed",
                last_checked_at=generated_at,
                message="Fetch timed out.",
                last_error="Fetch timed out.",
            )
        ],
    )

    source = report.source_health[0]
    assert source.status == "failed"
    assert source.severity == "critical"
    assert source.user_title == "Regulation source unavailable"
    assert source.affects_legal_status is True
    assert source.affects_score is True
    assert source.freshness_minutes == 0
    assert any(warning.source == "adfg_emergency_orders" for warning in report.warnings)


def test_ok_source_health_copy_reads_as_healthy() -> None:
    generated_at = datetime(2026, 7, 22, 22, 0, tzinfo=UTC)

    report = build_condition_report(
        generated_at,
        regulations=[],
        fish_counts=[],
        alerts=[],
        source_health=[
            SourceHealth(
                source="noaa_tides",
                status="ok",
                last_checked_at=generated_at,
                message="Fetched NOAA tides.",
            ),
            SourceHealth(
                source="usgs",
                status="ok",
                last_checked_at=generated_at,
                message="Fetched USGS water data.",
            ),
            SourceHealth(
                source="adfg_emergency_orders",
                status="ok",
                last_checked_at=generated_at,
                message="Fetched ADF&G orders.",
            ),
            SourceHealth(
                source="adfg_fish_counts",
                status="ok",
                last_checked_at=generated_at,
                message="Fetched ADF&G counts.",
            ),
            SourceHealth(
                source="adfg_fishing_reports",
                status="ok",
                last_checked_at=generated_at,
                message="Fetched ADF&G fishing reports.",
            ),
            SourceHealth(
                source="usgs_statistics",
                status="ok",
                last_checked_at=generated_at,
                message="Fetched USGS statistics.",
            ),
            SourceHealth(
                source="nws",
                status="ok",
                last_checked_at=generated_at,
                message="Fetched NWS.",
            ),
        ],
    )

    titles_by_source = {health.source: health.user_title for health in report.source_health}
    assert titles_by_source["noaa_tides"] == "Tide data current"
    assert titles_by_source["usgs"] == "Water data current"
    assert titles_by_source["adfg_fishing_reports"] == "Fishing report data current"
    assert "needs attention" not in " ".join(titles_by_source.values()).lower()
    assert report.warnings == []


def test_degraded_source_health_copy_keeps_warning_severity() -> None:
    generated_at = datetime(2026, 7, 22, 22, 0, tzinfo=UTC)

    report = build_condition_report(
        generated_at,
        regulations=[],
        fish_counts=[],
        alerts=[],
        source_health=[
            SourceHealth(
                source="usgs",
                status="ok",
                last_checked_at=datetime(2026, 7, 21, 21, 59, tzinfo=UTC),
                message="Fetched USGS water data.",
            )
        ],
    )

    source = report.source_health[0]
    assert source.status == "degraded"
    assert source.severity == "warning"
    assert source.user_title == "Water data needs attention"
    assert source.user_message == "Fetched USGS water data."
    assert any(
        warning.source == "usgs"
        and warning.severity == "warning"
        and warning.user_title == "Water data needs attention"
        for warning in report.warnings
    )


def test_failed_source_health_copy_reads_as_unavailable_without_losing_warning() -> None:
    generated_at = datetime(2026, 7, 22, 22, 0, tzinfo=UTC)

    report = build_condition_report(
        generated_at,
        regulations=[],
        fish_counts=[],
        alerts=[],
        source_health=[
            SourceHealth(
                source="noaa_tides",
                status="failed",
                last_checked_at=generated_at,
                message="NOAA tide fetch timed out.",
                last_error="NOAA tide fetch timed out.",
            )
        ],
    )

    source = report.source_health[0]
    assert source.status == "failed"
    assert source.severity == "warning"
    assert source.user_title == "Tide data unavailable"
    assert source.user_message == "NOAA tide fetch timed out."
    assert any(
        warning.source == "noaa_tides"
        and warning.severity == "warning"
        and warning.user_title == "Tide data unavailable"
        for warning in report.warnings
    )


def test_failed_usgs_source_suppresses_active_water_values_and_notes_cached_data() -> None:
    generated_at = datetime(2026, 7, 22, 22, 0, tzinfo=UTC)

    report = build_condition_report(
        generated_at,
        usgs_observations=parse_usgs_payload(_fixture("usgs_kenai_gages.json")),
        regulations=[],
        fish_counts=[],
        alerts=[],
        source_health=[
            SourceHealth(
                source="usgs",
                status="failed",
                last_checked_at=generated_at,
                message="USGS timed out.",
                last_error="USGS timed out.",
            ),
            SourceHealth(
                source="usgs_statistics",
                status="failed",
                last_checked_at=generated_at,
                message="USGS statistics timed out.",
                last_error="USGS statistics timed out.",
            ),
            SourceHealth(
                source="adfg_emergency_orders",
                status="ok",
                last_checked_at=generated_at,
                message="Fetched ADF&G orders.",
            ),
            SourceHealth(
                source="adfg_fish_counts",
                status="ok",
                last_checked_at=generated_at,
                message="Fetched ADF&G fish counts.",
            ),
            SourceHealth(
                source="nws",
                status="ok",
                last_checked_at=generated_at,
                message="Fetched NWS.",
            ),
            SourceHealth(
                source="noaa_tides",
                status="ok",
                last_checked_at=generated_at,
                message="Fetched NOAA tides.",
            ),
        ],
    )

    assert report.locations[0].water["discharge_cfs"] is None
    assert report.locations[0].water["data_status"] == "unavailable"
    assert any("USGS water source failed" in note for note in report.locations[0].notes)
    assert report.confidence < 0.72


def test_pdf_only_emergency_order_creates_manual_review_warning_and_alert() -> None:
    report = build_condition_report(
        datetime(2026, 7, 22, 22, 0, tzinfo=UTC),
        regulations=[
            Regulation(
                title="Emergency Order 2-KS-10-26",
                status="restricted",
                source_url="https://www.adfg.alaska.gov/static/orders/eo-2-ks-10-26.pdf",
                summary="PDF-only order requires manual review.",
                manual_review_required=True,
                content_type="pdf",
            )
        ],
        fish_counts=[],
        alerts=[],
    )

    assert report.emergency_orders[0].manual_review_required is True
    assert any(
        warning.user_title == "Emergency order needs manual review" for warning in report.warnings
    )
    review_alert = next(
        alert for alert in report.alerts if alert.title == "Manual review required for ADF&G order"
    )
    assert review_alert.advisory_explanation == (
        "This ADF&G emergency-order advisory means the official order could not be "
        "confidently parsed by the engine."
    )
    assert review_alert.fishing_impact == (
        "The legal details may change whether, where, or how a person can fish; verify "
        "the official ADF&G order before relying on this report."
    )


def test_unknown_manual_review_order_caps_v1_report_and_avoids_open_legal_copy() -> None:
    generated_at = datetime(2026, 7, 22, 22, 0, tzinfo=UTC)
    report = build_condition_report(
        generated_at,
        regulations=[
            Regulation(
                title="Emergency Order 2-KS-UNKNOWN",
                status="unknown",
                effective_date=generated_at.date(),
                summary="Order could not be confidently classified.",
                manual_review_required=True,
                content_type="html",
            )
        ],
        fish_counts=[
            FishCount(
                species="Sockeye",
                location="Kenai River late-run sockeye",
                count=35_000,
                observation_date=generated_at.date(),
            )
        ],
        alerts=[],
        source_health=[
            SourceHealth(
                source="adfg_emergency_orders",
                status="ok",
                last_checked_at=generated_at,
                message="Fetched ADF&G orders.",
            ),
            SourceHealth(
                source="adfg_fish_counts",
                status="ok",
                last_checked_at=generated_at,
                message="Fetched ADF&G counts.",
            ),
            SourceHealth(
                source="usgs",
                status="ok",
                last_checked_at=generated_at,
                message="Fetched USGS.",
            ),
            SourceHealth(
                source="usgs_statistics",
                status="ok",
                last_checked_at=generated_at,
                message="Fetched USGS statistics.",
            ),
            SourceHealth(
                source="nws",
                status="ok",
                last_checked_at=generated_at,
                message="Fetched NWS.",
            ),
            SourceHealth(
                source="noaa_tides",
                status="ok",
                last_checked_at=generated_at,
                message="Fetched NOAA tides.",
            ),
        ],
    )

    assert report.overall_status == "unknown"
    assert report.overall_score <= 45
    assert report.confidence < 0.72
    assert "not a legal permission" in report.locations[0].legal_explanation.lower()
    assert "verify" in report.locations[0].recommended_user_action.lower()
    assert "conditions look fishable" not in report.locations[0].recommended_user_action.lower()


def test_report_score_uses_usgs_and_sockeye_count_signals() -> None:
    observations = parse_usgs_payload(_fixture("usgs_kenai_gages.json"))
    fish_counts = [
        FishCount(
            species="Sockeye",
            location="Kenai River late-run sockeye",
            count=35_000,
            observation_date=datetime(2026, 7, 22, tzinfo=UTC).date(),
            source_url="https://www.adfg.alaska.gov/sf/FishCounts/",
        ),
        FishCount(
            species="Sockeye",
            location="Kenai River late-run sockeye",
            count=31_000,
            observation_date=datetime(2026, 7, 21, tzinfo=UTC).date(),
            source_url="https://www.adfg.alaska.gov/sf/FishCounts/",
        ),
        FishCount(
            species="Sockeye",
            location="Kenai River late-run sockeye",
            count=25_000,
            observation_date=datetime(2026, 7, 20, tzinfo=UTC).date(),
            source_url="https://www.adfg.alaska.gov/sf/FishCounts/",
        ),
    ]
    report = build_condition_report(
        datetime(2026, 7, 22, 22, 0, tzinfo=UTC),
        usgs_observations=observations,
        fish_counts=fish_counts,
        regulations=[],
        alerts=[],
        source_health=[
            SourceHealth(
                source="usgs",
                status="ok",
                last_checked_at=datetime(2026, 7, 22, 20, 0, tzinfo=UTC),
                message="Fetched USGS.",
            ),
            SourceHealth(
                source="adfg_fish_counts",
                status="ok",
                last_checked_at=datetime(2026, 7, 22, 18, 0, tzinfo=UTC),
                message="Fetched ADF&G counts.",
            ),
                SourceHealth(
                    source="adfg_emergency_orders",
                    status="ok",
                    last_checked_at=datetime(2026, 7, 22, 19, 0, tzinfo=UTC),
                    message="Fetched ADF&G orders.",
                ),
                SourceHealth(
                    source="usgs_statistics",
                    status="ok",
                    last_checked_at=datetime(2026, 7, 22, 19, 30, tzinfo=UTC),
                    message="Fetched USGS statistics.",
                ),
                SourceHealth(
                    source="nws",
                    status="ok",
                    last_checked_at=datetime(2026, 7, 22, 21, 0, tzinfo=UTC),
                    message="Fetched NWS.",
                ),
                SourceHealth(
                    source="noaa_tides",
                    status="ok",
                    last_checked_at=datetime(2026, 7, 22, 21, 0, tzinfo=UTC),
                    message="Fetched NOAA tides.",
                ),
            ],
        )

    assert report.overall_score > 72
    assert report.confidence >= 0.70
    assert report.overall_status == "excellent"
    assert any("USGS 00060" in note for note in report.locations[0].notes)
    assert any("Sockeye 3-day average" in note for note in report.locations[0].notes)


def test_location_scores_use_each_locations_mapped_gauge() -> None:
    generated_at = datetime(2026, 7, 22, 22, 0, tzinfo=UTC)
    observations = [
        _usgs_observation("15258000", "00060", 120, "ft3/s", generated_at),
        _usgs_observation("15258000", "00010", 1.0, "deg C", generated_at),
        _usgs_observation("15266300", "00060", 4200, "ft3/s", generated_at),
        _usgs_observation("15266300", "00010", 11.0, "deg C", generated_at),
    ]
    statistics = [
        UsgsFlowStatistic(
            site_id="15258000",
            month=7,
            day=22,
            parameter_code="00060",
            unit="ft3/s",
            p25=500,
            p50=900,
            p75=1400,
            p90=1800,
            p95=2200,
        ),
        UsgsFlowStatistic(
            site_id="15266300",
            month=7,
            day=22,
            parameter_code="00060",
            unit="ft3/s",
            p25=2500,
            p50=4000,
            p75=6000,
            p90=7500,
            p95=8300,
        ),
    ]

    report = build_condition_report(
        generated_at,
        usgs_observations=observations,
        fish_counts=[],
        regulations=[],
        alerts=[],
        usgs_flow_statistics=statistics,
    )

    upper = next(
        location for location in report.locations if location.id == "cooper_landing_upper_kenai"
    )
    soldotna = next(location for location in report.locations if location.id == "soldotna")

    assert upper.condition_score < soldotna.condition_score
    assert upper.status == "fair"
    assert "Cold water can slow fish movement and feeding." in upper.limiting_factors
    assert "Cold water can slow fish movement and feeding." not in soldotna.limiting_factors


def test_location_contract_exposes_component_scores_and_source_provenance() -> None:
    observations = parse_usgs_payload(_fixture("usgs_kenai_gages.json"))
    report = build_condition_report(
        datetime(2026, 7, 22, 9, 0, tzinfo=UTC),
        usgs_observations=observations,
        fish_counts=[],
        regulations=[],
        alerts=[],
        tide_predictions=[
            TidePrediction(
                station_id="9455742",
                predicted_at=datetime(2026, 7, 22, 6, 0, tzinfo=UTC),
                height_ft=2.1,
                tide_type="L",
            ),
            TidePrediction(
                station_id="9455742",
                predicted_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
                height_ft=20.4,
                tide_type="H",
            ),
        ],
    )

    lower = next(location for location in report.locations if location.id == "kenai_river_mouth")
    dumped = lower.model_dump(mode="json")

    assert dumped["component_scores"]["environmental"] >= 0
    assert dumped["component_scores"]["location"] >= 0
    assert dumped["component_scores"]["species"] >= 0
    assert any(source["source"] == "usgs" for source in dumped["source_provenance"])
    assert any(source["source"] == "noaa_tides" for source in dumped["source_provenance"])


def test_kenai_rm19_sockeye_counts_apply_only_to_lower_relevant_locations() -> None:
    report = build_condition_report(
        datetime(2026, 7, 22, 9, 0, tzinfo=UTC),
        usgs_observations=parse_usgs_payload(_fixture("usgs_kenai_gages.json")),
        fish_counts=[
            FishCount(
                species="Sockeye salmon",
                location="Kenai River RM19 sonar",
                count=35_000,
                observation_date=datetime(2026, 7, 22, tzinfo=UTC).date(),
                count_location_id="40",
                species_id="420",
                source_url="https://www.adfg.alaska.gov/sf/FishCounts/",
            )
        ],
        regulations=[],
        alerts=[],
    )

    upper = next(
        location for location in report.locations if location.id == "cooper_landing_upper_kenai"
    )
    middle = next(
        location for location in report.locations if location.id == "middle_kenai_skilak_outlet"
    )
    soldotna = next(location for location in report.locations if location.id == "soldotna")

    assert upper.sockeye_score is None
    assert middle.sockeye_score is None
    assert all(source["source"] != "adfg_fish_counts" for source in upper.source_provenance)
    assert all(source["source"] != "adfg_fish_counts" for source in middle.source_provenance)
    assert soldotna.sockeye_score is not None
    assert any(source["source"] == "adfg_fish_counts" for source in soldotna.source_provenance)


def test_adfg_count_signals_support_all_species_and_mapped_locations() -> None:
    generated_at = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)
    report = build_condition_report(
        generated_at,
        usgs_observations=parse_usgs_payload(_fixture("usgs_kenai_gages.json")),
        fish_counts=[
            FishCount(
                species="Sockeye",
                location="Kenai River (late-run sockeye)",
                count=35_000,
                observation_date=generated_at.date(),
                count_location_id="40",
                species_id="420",
            ),
            FishCount(
                species="Chinook - Late Run",
                location="Kenai River (Chinook)",
                count=125,
                observation_date=generated_at.date(),
                count_location_id="72",
                species_id="412",
            ),
            FishCount(
                species="Sockeye - Late Run",
                location="Russian River",
                count=2_800,
                observation_date=generated_at.date(),
                count_location_id="13",
                species_id="422",
            ),
        ],
        regulations=[],
        alerts=[],
    )

    russian = next(
        location for location in report.locations if location.id == "russian_river_confluence"
    )
    soldotna = next(location for location in report.locations if location.id == "soldotna")
    chinook = next(score for score in report.species_scores if score.species == "Chinook salmon")

    assert russian.sockeye_score is not None
    assert soldotna.chinook_score is not None
    assert soldotna.rainbow_trout_score is not None
    assert soldotna.chinook_score > soldotna.rainbow_trout_score
    assert chinook.score is not None
    assert chinook.status != "unknown"
    assert any(
        source["source"] == "adfg_fish_counts" and source["source_id"] == "13"
        for source in russian.source_provenance
    )
    assert any(
        source["source"] == "adfg_fish_counts" and source["source_id"] == "40"
        for source in soldotna.source_provenance
    )


def test_chinook_only_adfg_signal_influences_overall_score() -> None:
    generated_at = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)
    base_report = build_condition_report(
        generated_at,
        usgs_observations=parse_usgs_payload(_fixture("usgs_kenai_gages.json")),
        fish_counts=[],
        regulations=[],
        alerts=[],
    )
    chinook_report = build_condition_report(
        generated_at,
        usgs_observations=parse_usgs_payload(_fixture("usgs_kenai_gages.json")),
        fish_counts=[
            FishCount(
                species="Chinook - Late Run",
                location="Kenai River (Chinook)",
                count=125,
                observation_date=generated_at.date(),
                count_location_id="72",
                species_id="412",
            )
        ],
        regulations=[],
        alerts=[],
    )

    assert chinook_report.overall_score > base_report.overall_score


def test_report_notes_explain_weather_tide_and_flow_percentile_changes() -> None:
    observations = parse_usgs_payload(_fixture("usgs_kenai_gages.json"))
    report = build_condition_report(
        datetime(2026, 7, 22, 9, 0, tzinfo=UTC),
        usgs_observations=observations,
        fish_counts=[],
        regulations=[],
        alerts=[],
        weather_observations=[
            WeatherObservation(
                location="Kenai,AK",
                observed_at=datetime(2026, 7, 22, 8, 0, tzinfo=UTC),
                recent_rain_inches_24h=0.3,
                wind_mph=20,
                source="nws",
            )
        ],
        tide_predictions=[
            TidePrediction(
                station_id="9455742",
                predicted_at=datetime(2026, 7, 22, 6, 0, tzinfo=UTC),
                height_ft=2.1,
                tide_type="L",
            ),
            TidePrediction(
                station_id="9455742",
                predicted_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
                height_ft=20.4,
                tide_type="H",
            ),
        ],
        usgs_flow_statistics=[
            UsgsFlowStatistic(
                site_id="15266300",
                month=7,
                day=22,
                parameter_code="00060",
                unit="ft3/s",
                p25=2500,
                p50=4000,
                p75=6000,
                p90=7500,
                p95=8300,
            )
        ],
    )

    joined_notes = " ".join(report.locations[0].notes)
    assert "USGS flow percentile" in joined_notes
    assert "NWS forecast rain" in joined_notes
    assert "NWS wind" in joined_notes
    assert "NOAA tide stage" in joined_notes


def _source_health_message(report, source: str) -> str:
    return next(health.message for health in report.source_health if health.source == source)


def _usgs_observation(
    site_id: str,
    parameter_code: str,
    value: float,
    unit: str,
    observed_at: datetime,
) -> UsgsObservation:
    return UsgsObservation(
        site_id=site_id,
        monitoring_location_id=f"USGS-{site_id}",
        site_name=f"USGS {site_id}",
        parameter_code=parameter_code,
        parameter_name=parameter_code,
        value=value,
        unit=unit,
        observed_at=observed_at,
    )


def _fixture(name: str) -> str:
    return (Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8")
