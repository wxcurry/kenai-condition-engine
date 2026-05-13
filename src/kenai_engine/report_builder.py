"""Build app-facing condition reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from kenai_engine.models import (
    ENGINE_NAME,
    ENGINE_VERSION,
    SCHEMA_VERSION,
    Alert,
    BaselineRegulation,
    FishCount,
    FishCountTrend,
    LocationCondition,
    Regulation,
    Report,
    ScoreInput,
    SourceHealth,
    SourceWarning,
    SpeciesScore,
    TidePrediction,
    UsgsFlowStatistic,
    UsgsObservation,
    WeatherObservation,
)
from kenai_engine.scoring import FRESHNESS_LIMIT_HOURS, score_conditions
from kenai_engine.seasonal_sources import is_score_source_active
from kenai_engine.sources.noaa_tides import determine_tide_stage
from kenai_engine.sources.usgs import calculate_flow_percentile, classify_usgs_trend

REQUIRED_SCORE_SOURCES = {
    "usgs",
    "usgs_statistics",
    "adfg_emergency_orders",
    "adfg_fish_counts",
    "nws",
    "noaa_tides",
}
REPORT_TTL = timedelta(hours=6)


@dataclass(frozen=True)
class FishCountSignal:
    """Derived recent fish-count signal for a species and count location."""

    species_key: str
    location_key: str
    recent_avg: int
    latest_count: int
    trend: FishCountTrend
    latest_observation_date: date
    count_location_id: str | None = None
    species_id: str | None = None


DEFAULT_LOCATIONS = [
    {
        "id": "cooper_landing_upper_kenai",
        "name": "Cooper Landing / Upper Kenai",
        "segment": "upper",
        "lat": 60.489,
        "lon": -149.834,
        "monitoring_location_id": "USGS-15258000",
        "nwis_site_id": "15258000",
        "fishing_context": (
            "Upper river drift, wade, trout, dolly varden, and seasonal salmon access."
        ),
        "score_key": "upper_kenai",
    },
    {
        "id": "russian_river_confluence",
        "name": "Russian River Confluence",
        "segment": "upper",
        "lat": 60.489,
        "lon": -149.969,
        "fishing_context": (
            "Sockeye-focused confluence and sanctuary-area context; check ADF&G orders."
        ),
        "score_key": "upper_kenai",
        "monitoring_location_id": "USGS-15266010",
        "nwis_site_id": "15266010",
    },
    {
        "id": "middle_kenai_skilak_outlet",
        "name": "Skilak Lake Outlet / Middle Kenai",
        "segment": "middle",
        "lat": 60.477,
        "lon": -150.470,
        "fishing_context": "Middle river boat and drift context below Skilak Lake.",
        "score_key": "middle_kenai",
        "monitoring_location_id": "USGS-15266110",
        "nwis_site_id": "15266110",
    },
    {
        "id": "soldotna",
        "name": "Soldotna",
        "segment": "soldotna",
        "lat": 60.487,
        "lon": -151.058,
        "fishing_context": "High-use bank and boat access near Soldotna.",
        "score_key": "soldotna",
        "monitoring_location_id": "USGS-15266300",
        "nwis_site_id": "15266300",
    },
    {
        "id": "lower_kenai_tidewater",
        "name": "Lower Kenai / Tidewater",
        "segment": "lower",
        "lat": 60.553,
        "lon": -151.258,
        "fishing_context": "Lower river salmon movement influenced by tide stage and boat access.",
        "score_key": "lower_kenai",
        "monitoring_location_id": "USGS-15266300",
        "nwis_site_id": "15266300",
    },
    {
        "id": "kenai_river_mouth",
        "name": "Kenai River Mouth",
        "segment": "mouth",
        "lat": 60.554,
        "lon": -151.270,
        "fishing_context": (
            "Mouth and dipnet-adjacent context; strongly tide and regulation sensitive."
        ),
        "score_key": "lower_kenai",
        "monitoring_location_id": "USGS-15266300",
        "nwis_site_id": "15266300",
    },
]


def build_condition_report(
    now: datetime | None = None,
    usgs_observations: list[UsgsObservation] | None = None,
    regulations: list[Regulation] | None = None,
    fish_counts: list[FishCount] | None = None,
    alerts: list[Alert] | None = None,
    weather_observations: list[WeatherObservation] | None = None,
    tide_predictions: list[TidePrediction] | None = None,
    usgs_flow_statistics: list[UsgsFlowStatistic] | None = None,
    source_health: list[SourceHealth] | None = None,
    baseline_regulations: list[BaselineRegulation] | None = None,
) -> Report:
    """Build the app-facing Kenai River condition report."""

    generated_at = now or datetime.now(UTC)
    today = generated_at.date()
    observations = [] if usgs_observations is None else usgs_observations
    active_regulations = regulations if regulations is not None else [
        Regulation(
            title="No active emergency order detected",
            status="open",
            effective_date=today,
            source_url="https://www.adfg.alaska.gov/",
            summary="No active emergency-order record is available in the normalized source set.",
        )
    ]
    active_fish_counts = fish_counts if fish_counts is not None else [
        FishCount(
            species="Sockeye salmon",
            location="Kenai River",
            count=0,
            observation_date=today,
            source_url="https://www.adfg.alaska.gov/",
        )
    ]
    active_alerts = alerts if alerts is not None else [
        Alert(
            title="Source data unavailable",
            severity="info",
            summary="The condition report was generated without normalized alert records.",
            source="kenai-condition-engine",
        )
    ]
    active_weather = [] if weather_observations is None else weather_observations
    active_tides = [] if tide_predictions is None else tide_predictions
    active_flow_statistics = [] if usgs_flow_statistics is None else usgs_flow_statistics
    active_baseline_regulations = [] if baseline_regulations is None else baseline_regulations
    baseline_missing = baseline_regulations is not None and not active_baseline_regulations
    warn_on_source_health = source_health is not None
    active_source_health = (
        _default_source_health(
            generated_at,
            observations,
            active_regulations,
            active_fish_counts,
            active_alerts,
            usgs_observations,
            regulations,
            fish_counts,
            alerts,
        )
        if source_health is None
        else _enrich_source_health(generated_at, source_health)
    )
    usable_observations = observations if _source_is_usable(active_source_health, "usgs") else []
    usable_flow_statistics = (
        active_flow_statistics
        if _source_is_usable(active_source_health, "usgs_statistics")
        else []
    )
    score = score_conditions(
        _score_input_from_records(
            generated_at,
            usable_observations,
            active_regulations,
            active_fish_counts,
            active_alerts,
            active_weather,
            active_tides,
            usable_flow_statistics,
            active_source_health,
        )
    )
    warnings = (
        _build_warnings(generated_at, active_source_health, active_regulations)
        if warn_on_source_health
        else _manual_review_warnings(active_regulations)
    )
    if baseline_missing:
        warnings.append(
            SourceWarning(
                source="baseline_regulations",
                severity="warning",
                user_title="Baseline regulations need review",
                user_message=(
                    "No structured baseline regulation record is available; emergency orders "
                    "alone do not define full legal status."
                ),
                affects_score=True,
                affects_legal_status=True,
            )
        )
    manual_review_alerts = _manual_review_alerts(active_regulations)
    if manual_review_alerts:
        active_alerts = [*active_alerts, *manual_review_alerts]
    report_confidence = score.confidence
    if baseline_missing:
        report_confidence = max(0.05, round(report_confidence - 0.2, 2))
    location_notes = score.reasons
    if usable_observations:
        location_notes = [
            *[_format_usgs_note(observation) for observation in usable_observations[:3]],
            *_fish_count_notes(active_fish_counts),
            *_weather_notes(active_weather),
            *_tide_notes(active_tides, generated_at),
            *_flow_percentile_notes(usable_observations, usable_flow_statistics, generated_at),
            *score.reasons,
        ]
    elif observations and not _source_is_usable(active_source_health, "usgs"):
        location_notes = [
            "USGS water source failed; cached water readings are withheld from active conditions.",
            *score.reasons,
        ]

    return Report(
        schema_version=SCHEMA_VERSION,
        engine_version=ENGINE_VERSION,
        generated_by=ENGINE_NAME,
        report_date=today,
        generated_at=generated_at,
        expires_at=generated_at + REPORT_TTL,
        report_status=_report_status(active_source_health),
        river="Kenai River",
        overall_score=score.overall_score,
        overall_status=score.overall_status,
        confidence=report_confidence,
        confidence_band=_confidence_band(report_confidence),
        summary=_build_summary(
            score.overall_status,
            usable_observations,
            active_alerts,
            generated_at,
            active_source_health if warn_on_source_health else [],
        ),
        locations=_build_locations(
            score,
            report_confidence,
            location_notes,
            usable_observations,
            active_regulations,
            active_fish_counts,
            active_weather,
            active_alerts,
            active_tides,
            usable_flow_statistics,
            active_source_health,
            generated_at,
        ),
        species_scores=_build_species_scores(score, report_confidence, active_fish_counts),
        baseline_regulations=active_baseline_regulations,
        emergency_orders=active_regulations,
        regulations=active_regulations,
        fish_counts=active_fish_counts,
        alerts=active_alerts,
        warnings=warnings,
        source_health=active_source_health,
    )


build_placeholder_report = build_condition_report


def write_latest_report(output_dir: Path, report: Report | None = None) -> Path:
    """Write `latest.json` and return its path."""

    output_dir.mkdir(parents=True, exist_ok=True)
    latest_path = output_dir / "latest.json"
    report_to_write = report or build_condition_report()
    latest_path.write_text(
        json.dumps(report_to_write.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    return latest_path


def load_report(path: Path) -> Report:
    """Load and validate a report JSON file."""

    return Report.model_validate_json(path.read_text(encoding="utf-8"))


def _score_input_from_records(
    generated_at: datetime,
    usgs_observations: list[UsgsObservation],
    regulations: list[Regulation],
    fish_counts: list[FishCount],
    alerts: list[Alert],
    weather_observations: list[WeatherObservation],
    tide_predictions: list[TidePrediction],
    usgs_flow_statistics: list[UsgsFlowStatistic],
    source_health: list[SourceHealth],
) -> ScoreInput:
    latest_observations = {
        observation.parameter_code: observation for observation in usgs_observations
    }
    water_temperature_f = _water_temperature_f(latest_observations.get("00010"))
    sockeye_counts = [
        count
        for count in fish_counts
        if "sockeye" in count.species.lower() and "kenai" in count.location.lower()
    ]
    all_signals = _fish_count_signals(fish_counts)
    signals = _best_signals_by_species(all_signals)
    primary_signal = _primary_fish_count_signal(all_signals)
    fish_count_3day_avg = _three_day_average(sockeye_counts)
    weather = _latest_weather(weather_observations)
    flow_percentile = _current_flow_percentile(
        generated_at,
        latest_observations,
        usgs_flow_statistics,
    )
    tide_stage = determine_tide_stage(tide_predictions, generated_at) if tide_predictions else None
    flood_alerts = [alert for alert in alerts if "flood" in alert.title.lower()]

    return ScoreInput(
        active_closure=any(
            regulation.status == "closed"
            for regulation in _active_regulations_for_date(regulations, generated_at)
        ),
        active_restriction=any(
            regulation.status == "restricted"
            for regulation in _active_regulations_for_date(regulations, generated_at)
        ),
        legal_uncertainty=any(
            regulation.status == "unknown" or regulation.manual_review_required
            for regulation in _active_regulations_for_date(regulations, generated_at)
        ),
        location=_score_location_for_signal(primary_signal) or (
            "lower_kenai" if sockeye_counts else "soldotna"
        ),
        species=primary_signal.species_key
        if primary_signal
        else ("sockeye" if sockeye_counts else None),
        water_temperature_f=water_temperature_f,
        flow_percentile=flow_percentile,
        recent_rain_inches_24h=weather.recent_rain_inches_24h if weather else None,
        wind_mph=weather.wind_mph if weather else None,
        air_temperature_f=weather.temperature_f if weather else None,
        precipitation_probability=weather.precipitation_probability if weather else None,
        tide_stage=tide_stage,
        fish_count_3day_avg=fish_count_3day_avg,
        fish_count_trend=_fish_count_trend(sockeye_counts),
        fish_count_3day_avg_by_species={
            species: signal.recent_avg for species, signal in signals.items()
        },
        fish_count_trend_by_species={species: signal.trend for species, signal in signals.items()},
        flood_alert_active=any(alert.severity in {"watch", "warning"} for alert in flood_alerts),
        flood_alert_severity="warning"
        if any(alert.severity == "warning" for alert in flood_alerts)
        else "watch",
        source_freshness_hours=_source_freshness_hours(generated_at, source_health),
        missing_sources=_missing_score_sources_for_date(generated_at, source_health),
    )


def _format_usgs_note(observation: UsgsObservation) -> str:
    return (
        f"USGS {observation.parameter_code} at {observation.site_name}: "
        f"{observation.value:g} {observation.unit}"
    )


def _source_is_usable(source_health: list[SourceHealth], source: str) -> bool:
    matching = [health for health in source_health if health.source == source]
    if not matching:
        return True
    return all(health.status == "ok" for health in matching)


def _build_locations(
    score,
    report_confidence: float,
    notes: list[str],
    observations: list[UsgsObservation],
    regulations: list[Regulation],
    fish_counts: list[FishCount],
    weather_observations: list[WeatherObservation],
    alerts: list[Alert],
    tide_predictions: list[TidePrediction],
    usgs_flow_statistics: list[UsgsFlowStatistic],
    source_health: list[SourceHealth],
    generated_at: datetime,
) -> list[LocationCondition]:
    latest = _latest_observations_by_site_and_parameter(observations)
    weather = _latest_weather(weather_observations)
    tide_stage = determine_tide_stage(tide_predictions, generated_at) if tide_predictions else None
    base_confidence = report_confidence if observations else max(0.05, report_confidence - 0.1)
    locations: list[LocationCondition] = []
    for location in DEFAULT_LOCATIONS:
        site_id = location.get("nwis_site_id")
        site_latest = _site_latest(latest, site_id if isinstance(site_id, str) else None)
        site_observations = [
            observation
            for observation in observations
            if not isinstance(site_id, str) or observation.site_id == site_id
        ]
        trend = (
            classify_usgs_trend(site_observations, parameter_code="00065")
            if site_observations
            else {}
        )
        flow = site_latest.get("00060")
        stage = site_latest.get("00065")
        temp = site_latest.get("00010")
        turbidity = site_latest.get("63680")
        conductance = site_latest.get("00095")
        oxygen = site_latest.get("00300")
        ph = site_latest.get("00400")
        observed_at = _latest_observed_at(site_latest)
        local_score_input = _score_input_from_location_records(
            generated_at,
            location,
            site_latest,
            regulations,
            fish_counts,
            alerts,
            weather,
            tide_predictions,
            usgs_flow_statistics,
            source_health,
            trend,
        )
        local_score = score_conditions(local_score_input)
        condition_score = local_score.location_scores.get(
            str(location["score_key"]),
            local_score.overall_score,
        )
        relevant_fish_counts = _fish_counts_for_location(location, fish_counts)
        component_scores = _component_scores(local_score_input, local_score)
        site_usgs_notes = [_format_usgs_note(observation) for observation in site_latest.values()]
        has_local_flow_note = any("USGS 00060" in note for note in site_usgs_notes)
        fallback_usgs_notes = (
            [note for note in notes if note.startswith("USGS 00060")]
            if not has_local_flow_note
            else []
        )
        location_notes = [
            *site_usgs_notes,
            *fallback_usgs_notes,
            *[note for note in notes if not note.startswith("USGS 000")],
        ]
        if not observations:
            location_notes = [
                "No current USGS water reading matched this location; confidence reduced.",
                *location_notes,
            ]
        water_data_status = "current" if site_latest else "unavailable"
        locations.append(
            LocationCondition(
                id=str(location["id"]),
                name=str(location["name"]),
                segment=str(location["segment"]),
                lat=float(location["lat"]),
                lon=float(location["lon"]),
                fishing_context=str(location["fishing_context"]),
                condition_score=condition_score,
                score=condition_score,
                status=local_score.overall_status,
                confidence=base_confidence,
                water={
                    "monitoring_location_id": location.get("monitoring_location_id")
                    or (flow.monitoring_location_id if flow else None),
                    "nwis_site_id": location.get("nwis_site_id")
                    or (flow.site_id if flow else None),
                    "discharge_cfs": flow.value if flow else None,
                    "gage_height_ft": stage.value if stage else None,
                    "water_temp_c": temp.value if temp and _is_celsius(temp.unit) else None,
                    "water_temp_f": _water_temperature_f(temp),
                    "turbidity_fnu": turbidity.value if turbidity else None,
                    "specific_conductance_us_cm": conductance.value if conductance else None,
                    "dissolved_oxygen_mg_l": oxygen.value if oxygen else None,
                    "ph": ph.value if ph else None,
                    "trend": trend.get("classification", "unknown"),
                    "trend_window_minutes": trend.get("window_minutes"),
                    "observed_at": observed_at.isoformat() if observed_at else None,
                    "source": "USGS",
                    "data_status": water_data_status,
                    "tide_stage": tide_stage if location["score_key"] == "lower_kenai" else None,
                },
                weather=_location_weather_payload(weather, turbidity, trend),
                alerts=[alert.title for alert in alerts],
                notes=location_notes,
                bank_fishing_score=max(
                    0,
                    condition_score - 5 if flow and flow.value > 8000 else condition_score,
                ),
                boat_fishing_score=max(
                    0,
                    condition_score - 8
                    if weather and weather.wind_mph and weather.wind_mph >= 20
                    else condition_score,
                ),
                sockeye_score=local_score.species_scores.get("sockeye")
                if relevant_fish_counts
                else None,
                chinook_score=local_score.species_scores.get("chinook"),
                coho_score=local_score.species_scores.get("coho"),
                rainbow_trout_score=local_score.species_scores.get("rainbow_trout"),
                dolly_varden_score=local_score.species_scores.get("dolly_varden"),
                score_delta_reason=local_score.score_delta_reason,
                contributing_factors=local_score.contributing_factors,
                limiting_factors=local_score.limiting_factors,
                confidence_explanation=local_score.confidence_explanation,
                legal_explanation=local_score.legal_explanation,
                recommended_user_action=local_score.recommended_user_action,
                component_scores=component_scores,
                source_provenance=_source_provenance_for_location(
                    location,
                    site_latest,
                    weather,
                    tide_predictions,
                    fish_counts,
                    generated_at,
                ),
            )
        )
    return locations


def _score_input_from_location_records(
    generated_at: datetime,
    location: dict[str, object],
    site_latest: dict[str, UsgsObservation],
    regulations: list[Regulation],
    fish_counts: list[FishCount],
    alerts: list[Alert],
    weather: WeatherObservation | None,
    tide_predictions: list[TidePrediction],
    usgs_flow_statistics: list[UsgsFlowStatistic],
    source_health: list[SourceHealth],
    trend: dict[str, object],
) -> ScoreInput:
    relevant_fish_counts = _fish_counts_for_location(location, fish_counts)
    relevant_signals = _fish_count_signals_for_location(location, fish_counts)
    best_signals = _best_signals_by_species(relevant_signals)
    tide_stage = (
        determine_tide_stage(tide_predictions, generated_at)
        if location.get("score_key") == "lower_kenai" and tide_predictions
        else None
    )
    trend_delta = trend.get("delta")

    return ScoreInput(
        active_closure=any(
            regulation.status == "closed"
            for regulation in _active_regulations_for_date(regulations, generated_at)
        ),
        active_restriction=any(
            regulation.status == "restricted"
            for regulation in _active_regulations_for_date(regulations, generated_at)
        ),
        legal_uncertainty=any(
            regulation.status == "unknown" or regulation.manual_review_required
            for regulation in _active_regulations_for_date(regulations, generated_at)
        ),
        location=str(location["score_key"]),
        species="sockeye" if relevant_fish_counts else None,
        water_temperature_f=_water_temperature_f(site_latest.get("00010")),
        flow_percentile=_current_flow_percentile(
            generated_at,
            site_latest,
            usgs_flow_statistics,
        ),
        gage_height_trend_ft_24h=trend_delta if isinstance(trend_delta, int | float) else None,
        recent_rain_inches_24h=weather.recent_rain_inches_24h if weather else None,
        wind_mph=weather.wind_mph if weather else None,
        air_temperature_f=weather.temperature_f if weather else None,
        precipitation_probability=weather.precipitation_probability if weather else None,
        tide_stage=tide_stage,
        fish_count_3day_avg=_three_day_average(relevant_fish_counts),
        fish_count_trend=_fish_count_trend(relevant_fish_counts),
        fish_count_3day_avg_by_species={
            species: signal.recent_avg for species, signal in best_signals.items()
        },
        fish_count_trend_by_species={
            species: signal.trend for species, signal in best_signals.items()
        },
        fish_count_location_adjustments={
            str(location["score_key"]): _location_signal_adjustment(relevant_signals)
        }
        if relevant_signals
        else {},
        flood_alert_active=any(
            "flood" in alert.title.lower() and alert.severity in {"watch", "warning"}
            for alert in alerts
        ),
        flood_alert_severity="warning"
        if any("flood" in alert.title.lower() and alert.severity == "warning" for alert in alerts)
        else "watch",
        source_freshness_hours=_source_freshness_hours(generated_at, source_health),
        missing_sources=_missing_score_sources_for_date(generated_at, source_health),
    )


def _fish_counts_for_location(
    location: dict[str, object],
    fish_counts: list[FishCount],
) -> list[FishCount]:
    location_keys = _count_location_keys_for_report_location(location)
    if location_keys:
        return [
            count
            for count in fish_counts
            if _species_key(count.species) == "sockeye"
            and _count_location_key(count.location) in location_keys
        ]

    return []


def _fish_count_signals_for_location(
    location: dict[str, object],
    fish_counts: list[FishCount],
) -> list[FishCountSignal]:
    location_keys = _count_location_keys_for_report_location(location)
    if not location_keys:
        return []
    return [
        signal
        for signal in _fish_count_signals(fish_counts)
        if signal.location_key in location_keys
    ]


def _count_location_keys_for_report_location(location: dict[str, object]) -> set[str]:
    location_text = f"{location.get('id', '')} {location.get('name', '')}".lower()
    if "russian" in location_text:
        return {"russian"}
    if not _location_supports_kenai_rm19_counts(location):
        return set()
    return {"kenai"}


def _fish_count_signals(fish_counts: list[FishCount]) -> list[FishCountSignal]:
    groups: dict[tuple[str, str], list[FishCount]] = {}
    for fish_count in fish_counts:
        species_key = _species_key(fish_count.species)
        location_key = _count_location_key(fish_count.location)
        if species_key is None or location_key is None:
            continue
        groups.setdefault((species_key, location_key), []).append(fish_count)

    return [
        _fish_count_signal_from_group(species_key, location_key, group)
        for (species_key, location_key), group in groups.items()
    ]


def _fish_count_signal_from_group(
    species_key: str,
    location_key: str,
    fish_counts: list[FishCount],
) -> FishCountSignal:
    latest_counts = sorted(fish_counts, key=lambda count: count.observation_date, reverse=True)[:3]
    latest = latest_counts[0]
    return FishCountSignal(
        species_key=species_key,
        location_key=location_key,
        recent_avg=_three_day_average(latest_counts) or 0,
        latest_count=latest.count,
        trend=_fish_count_trend(latest_counts),
        latest_observation_date=latest.observation_date,
        count_location_id=latest.count_location_id,
        species_id=latest.species_id,
    )


def _best_signals_by_species(signals: list[FishCountSignal]) -> dict[str, FishCountSignal]:
    best: dict[str, FishCountSignal] = {}
    for signal in signals:
        current = best.get(signal.species_key)
        if current is None or _signal_rank(signal) > _signal_rank(current):
            best[signal.species_key] = signal
    return best


def _primary_fish_count_signal(signals: list[FishCountSignal]) -> FishCountSignal | None:
    return max(signals, key=_signal_rank, default=None)


def _signal_rank(signal: FishCountSignal) -> tuple[date, int]:
    return signal.latest_observation_date, signal.recent_avg


def _score_location_for_signal(signal: FishCountSignal | None) -> str | None:
    if signal is None:
        return None
    if signal.location_key == "kenai":
        return "lower_kenai"
    if signal.location_key == "russian":
        return "upper_kenai"
    return None


def _species_key(species: str) -> str | None:
    normalized = species.lower()
    if "sockeye" in normalized:
        return "sockeye"
    if "chinook" in normalized or "king" in normalized:
        return "chinook"
    if "coho" in normalized or "silver" in normalized:
        return "coho"
    return None


def _count_location_key(location: str) -> str | None:
    normalized = location.lower()
    if "russian" in normalized:
        return "russian"
    if "kenai" in normalized:
        return "kenai"
    if "kasilof" in normalized:
        return "kasilof"
    return None


def _location_signal_adjustment(signals: list[FishCountSignal]) -> int:
    if not signals:
        return 0
    return max(_signal_location_adjustment(signal) for signal in signals)


def _signal_location_adjustment(signal: FishCountSignal) -> int:
    adjustment = 0
    if signal.trend == "rising":
        adjustment += 4
    elif signal.trend == "falling":
        adjustment -= 3

    if signal.species_key == "sockeye":
        if signal.recent_avg >= 30_000:
            adjustment += 6
        elif signal.recent_avg >= 10_000:
            adjustment += 3
        elif signal.recent_avg < 2_000:
            adjustment -= 4
    elif signal.species_key == "chinook":
        if signal.recent_avg >= 100:
            adjustment += 4
        elif signal.recent_avg == 0:
            adjustment -= 3
    elif signal.species_key == "coho":
        if signal.recent_avg >= 1_000:
            adjustment += 4
        elif signal.recent_avg == 0:
            adjustment -= 3
    return max(-8, min(8, adjustment))


def _location_supports_kenai_rm19_counts(location: dict[str, object]) -> bool:
    location_id = str(location.get("id", "")).lower()
    score_key = str(location.get("score_key", "")).lower()
    segment = str(location.get("segment", "")).lower()
    return (
        "soldotna" in location_id
        or score_key == "lower_kenai"
        or segment in {"soldotna", "lower", "mouth"}
    )


def _component_scores(score_input: ScoreInput, score) -> dict[str, int]:
    environmental = score_conditions(
        score_input.model_copy(update={"location": None, "species": None})
    ).overall_score
    return {
        "environmental": environmental,
        "location": score.location_scores.get(score_input.location or "", environmental),
        "species": score.species_scores.get(score_input.species or "", environmental),
        "overall": score.overall_score,
    }


def _source_provenance_for_location(
    location: dict[str, object],
    site_latest: dict[str, UsgsObservation],
    weather: WeatherObservation | None,
    tide_predictions: list[TidePrediction],
    fish_counts: list[FishCount],
    generated_at: datetime,
) -> list[dict[str, object | None]]:
    provenance: list[dict[str, object | None]] = []
    if site_latest:
        observed_at = _latest_observed_at(site_latest)
        provenance.append(
            {
                "source": "usgs",
                "source_id": location.get("nwis_site_id"),
                "observed_at": observed_at.isoformat() if observed_at else None,
                "retrieved_at": None,
                "role": "local_water",
            }
        )
    if weather is not None:
        provenance.append(
            {
                "source": "nws",
                "source_id": weather.source,
                "observed_at": weather.observed_at.isoformat(),
                "retrieved_at": None,
                "role": "weather",
            }
        )
    if location.get("score_key") == "lower_kenai" and tide_predictions:
        provenance.append(
            {
                "source": "noaa_tides",
                "source_id": tide_predictions[0].station_id,
                "observed_at": None,
                "retrieved_at": generated_at.isoformat(),
                "role": "tide_stage",
            }
        )
    relevant_fish_counts = _fish_counts_for_location(location, fish_counts)
    if relevant_fish_counts:
        latest_count = max(relevant_fish_counts, key=lambda count: count.observation_date)
        provenance.append(
            {
                "source": "adfg_fish_counts",
                "source_id": latest_count.count_location_id,
                "observed_at": latest_count.observation_date.isoformat(),
                "retrieved_at": None,
                "role": "species_activity",
            }
        )
    return provenance


def _build_species_scores(
    score,
    confidence: float,
    fish_counts: list[FishCount],
) -> list[SpeciesScore]:
    supported_species = {
        "sockeye": any("sockeye" in count.species.lower() for count in fish_counts),
        "chinook": any(
            "chinook" in count.species.lower() or "king" in count.species.lower()
            for count in fish_counts
        ),
        "coho": any("coho" in count.species.lower() for count in fish_counts),
        "rainbow_trout": False,
        "dolly_varden": False,
    }
    labels = {
        "sockeye": "Sockeye salmon",
        "chinook": "Chinook salmon",
        "coho": "Coho salmon",
        "rainbow_trout": "Rainbow trout",
        "dolly_varden": "Dolly Varden",
    }
    results: list[SpeciesScore] = []
    for key, label in labels.items():
        if supported_species[key] and key in score.species_scores:
            species_score = score.species_scores[key]
            results.append(
                SpeciesScore(
                    species=label,
                    score=species_score,
                    status=_status_from_score(species_score),
                    confidence=confidence,
                    explanation="Score supported by current official fish-count records.",
                    source="adfg_fish_counts",
                )
            )
        else:
            results.append(
                SpeciesScore(
                    species=label,
                    score=None,
                    status="unknown",
                    confidence=max(0.05, confidence - 0.25),
                    explanation="No current species-specific official count supports a score.",
                )
            )
    return results


def _fish_count_notes(fish_counts: list[FishCount]) -> list[str]:
    average = _three_day_average(
        [
            count
            for count in fish_counts
            if "sockeye" in count.species.lower() and "kenai" in count.location.lower()
        ]
    )
    if average is None:
        return []
    return [f"Sockeye 3-day average: {average:,} fish from ADF&G count records."]


def _weather_notes(weather_observations: list[WeatherObservation]) -> list[str]:
    weather = _latest_weather(weather_observations)
    if weather is None:
        return []
    notes: list[str] = []
    if weather.recent_rain_inches_24h is not None:
        notes.append(f"NWS forecast rain: {weather.recent_rain_inches_24h:g} inches in 24h.")
    if weather.wind_mph is not None:
        notes.append(f"NWS wind: {weather.wind_mph:g} mph.")
    return notes


def _location_weather_payload(
    weather: WeatherObservation | None,
    turbidity: UsgsObservation | None,
    trend: dict[str, object],
) -> dict[str, object | None]:
    return {
        "recent_rain_inches_24h": weather.recent_rain_inches_24h if weather else None,
        "wind_mph": weather.wind_mph if weather else None,
        "wind_direction": weather.wind_direction if weather else None,
        "temperature_f": weather.temperature_f if weather else None,
        "short_forecast": weather.short_forecast if weather else None,
        "precipitation_probability": weather.precipitation_probability if weather else None,
        "detailed_forecast": weather.detailed_forecast if weather else None,
        "weather_summary": weather.short_forecast if weather else None,
        "wind": _format_wind(weather),
        "rain_chance": _format_rain_chance(weather),
        "clarity": _clarity_label(turbidity, weather, trend),
        "clarity_source": _clarity_source(turbidity, weather, trend),
    }


def _format_wind(weather: WeatherObservation | None) -> str | None:
    if weather is None or weather.wind_mph is None:
        return None
    wind = f"{weather.wind_mph:g} mph"
    if weather.wind_direction:
        return f"{wind} {weather.wind_direction}"
    return wind


def _format_rain_chance(weather: WeatherObservation | None) -> str | None:
    if weather is None or weather.precipitation_probability is None:
        return None
    return f"{weather.precipitation_probability}%"


def _clarity_label(
    turbidity: UsgsObservation | None,
    weather: WeatherObservation | None,
    trend: dict[str, object],
) -> str:
    if turbidity is not None:
        if turbidity.value <= 5:
            return "clear"
        if turbidity.value <= 10:
            return "slightly_stained"
        if turbidity.value <= 20:
            return "stained"
        return "muddy"

    recent_rain = weather.recent_rain_inches_24h if weather else None
    trend_classification = str(trend.get("classification", "unknown"))
    if recent_rain is not None and recent_rain >= 0.75:
        return "reduced_estimated"
    if trend_classification == "rising":
        return "reduced_estimated"
    return "unknown"


def _clarity_source(
    turbidity: UsgsObservation | None,
    weather: WeatherObservation | None,
    trend: dict[str, object],
) -> str | None:
    if turbidity is not None:
        return "measured_turbidity"
    if (weather and weather.recent_rain_inches_24h is not None) or trend.get(
        "classification"
    ) not in {None, "unknown"}:
        return "flow_rain_estimate"
    return None


def _tide_notes(tide_predictions: list[TidePrediction], generated_at: datetime) -> list[str]:
    if not tide_predictions:
        return []
    return [f"NOAA tide stage: {determine_tide_stage(tide_predictions, generated_at)}."]


def _flow_percentile_notes(
    observations: list[UsgsObservation],
    statistics: list[UsgsFlowStatistic],
    generated_at: datetime,
) -> list[str]:
    percentile = _current_flow_percentile(
        generated_at,
        {observation.parameter_code: observation for observation in observations},
        statistics,
    )
    if percentile is None:
        return []
    return [f"USGS flow percentile: {percentile:g} for the current day-of-year."]


def _water_temperature_f(observation: UsgsObservation | None) -> float | None:
    if observation is None:
        return None
    if _is_celsius(observation.unit):
        return observation.value * 9 / 5 + 32
    if observation.unit.lower() in {"deg f", "f", "fahrenheit"}:
        return observation.value
    return None


def _is_celsius(unit: str) -> bool:
    return unit.lower() in {"deg c", "degc", "c", "celsius"}


def _latest_observations_by_site_and_parameter(
    observations: list[UsgsObservation],
) -> dict[str, dict[str, UsgsObservation]]:
    latest: dict[str, dict[str, UsgsObservation]] = {}
    for observation in sorted(observations, key=lambda item: item.observed_at, reverse=True):
        site_records = latest.setdefault(observation.site_id, {})
        site_records.setdefault(observation.parameter_code, observation)
    return latest


def _site_latest(
    latest: dict[str, dict[str, UsgsObservation]],
    site_id: str | None,
) -> dict[str, UsgsObservation]:
    if site_id and site_id in latest:
        return latest[site_id]
    if site_id:
        return {}
    return next(iter(latest.values()), {})


def _latest_observed_at(site_latest: dict[str, UsgsObservation]) -> datetime | None:
    if not site_latest:
        return None
    return max(observation.observed_at for observation in site_latest.values())


def _status_from_score(score: int) -> str:
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "good"
    if score >= 40:
        return "fair"
    return "poor"


def _latest_weather(weather_observations: list[WeatherObservation]) -> WeatherObservation | None:
    if not weather_observations:
        return None
    return max(weather_observations, key=lambda weather: weather.observed_at)


def _current_flow_percentile(
    generated_at: datetime,
    latest_observations: dict[str, UsgsObservation],
    statistics: list[UsgsFlowStatistic],
) -> float | None:
    flow_observation = latest_observations.get("00060")
    if flow_observation is None:
        return None
    matching_stats = [
        statistic
        for statistic in statistics
        if statistic.site_id == flow_observation.site_id
        and statistic.month == generated_at.month
        and statistic.day == generated_at.day
    ]
    if not matching_stats:
        return None
    return calculate_flow_percentile(flow_observation.value, matching_stats[0])


def _three_day_average(fish_counts: list[FishCount]) -> int | None:
    if not fish_counts:
        return None
    latest_counts = sorted(fish_counts, key=lambda count: count.observation_date, reverse=True)[:3]
    return round(sum(count.count for count in latest_counts) / len(latest_counts))


def _fish_count_trend(fish_counts: list[FishCount]) -> str:
    latest_counts = sorted(fish_counts, key=lambda count: count.observation_date, reverse=True)[:3]
    if len(latest_counts) < 2:
        return "unknown"
    newest = latest_counts[0].count
    oldest = latest_counts[-1].count
    if newest > oldest:
        return "rising"
    if newest < oldest:
        return "falling"
    return "steady"


def _source_freshness_hours(
    generated_at: datetime,
    source_health: list[SourceHealth],
) -> dict[str, float]:
    freshness: dict[str, float] = {}
    for health in source_health:
        checked_at = health.last_checked_at
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=UTC)
        freshness[health.source] = max(0.0, (generated_at - checked_at).total_seconds() / 3600)
    return freshness


def _report_status(source_health: list[SourceHealth]) -> str:
    if not source_health:
        return "degraded"
    if all(health.status == "failed" for health in source_health):
        return "failed"
    if any(health.status != "ok" for health in source_health):
        return "degraded"
    return "ok"


def _confidence_band(confidence: float) -> str:
    if confidence >= 0.7:
        return "high"
    if confidence >= 0.4:
        return "medium"
    return "low"


def _missing_score_sources_for_date(
    generated_at: datetime,
    source_health: list[SourceHealth],
) -> list[str]:
    if not source_health:
        return []
    available = {health.source for health in source_health if health.status != "failed"}
    required_sources = _required_score_sources_for_date(generated_at)
    return sorted(required_sources - available)


def _build_summary(
    status: str,
    usgs_observations: list[UsgsObservation],
    alerts: list[Alert],
    generated_at: datetime,
    source_health: list[SourceHealth],
) -> str:
    real_alerts = [alert for alert in alerts if alert.source != "kenai-condition-engine"]
    source_warning = _source_warning_summary(generated_at, source_health)
    if status == "closed":
        summary = "Active emergency order indicates a closure. Check official ADFG sources."
        return _prefix_source_warning(summary, source_warning)
    if status == "restricted":
        summary = "Active emergency order indicates restrictions. Check official ADFG sources."
        return _prefix_source_warning(summary, source_warning)
    if usgs_observations and real_alerts:
        summary = "Production condition report with normalized USGS readings and source alerts."
        return _prefix_source_warning(summary, source_warning)
    if usgs_observations:
        summary = "Production condition report with normalized USGS readings."
        return _prefix_source_warning(summary, source_warning)
    if real_alerts:
        summary = "Production condition report with source alerts."
        return _prefix_source_warning(summary, source_warning)
    summary = "Production condition report generated from currently available normalized sources."
    return _prefix_source_warning(summary, source_warning)


def _source_warning_summary(
    generated_at: datetime,
    source_health: list[SourceHealth],
) -> str:
    if not source_health:
        return ""

    missing_sources = _missing_score_sources_for_date(generated_at, source_health)
    if missing_sources:
        return f"Source warning: missing required sources ({', '.join(missing_sources)})."

    stale_sources = _stale_required_sources(generated_at, source_health)
    if stale_sources:
        return f"Source warning: stale required sources ({', '.join(stale_sources)})."

    problem_sources = sorted(health.source for health in source_health if health.status == "failed")
    if problem_sources:
        return f"Source warning: source errors ({', '.join(problem_sources)})."

    return ""


def _build_warnings(
    generated_at: datetime,
    source_health: list[SourceHealth],
    regulations: list[Regulation],
) -> list[SourceWarning]:
    warnings: list[SourceWarning] = []
    for health in source_health:
        if health.severity in {"watch", "warning", "critical"}:
            warnings.append(
                SourceWarning(
                    source=health.source,
                    severity=health.severity,
                    user_title=health.user_title,
                    user_message=health.user_message,
                    affects_score=health.affects_score,
                    affects_legal_status=health.affects_legal_status,
                )
            )
    for source in _missing_score_sources_for_date(generated_at, source_health):
        warnings.append(_source_warning_for_missing(source))
    for source in _stale_required_sources(generated_at, source_health):
        if not any(warning.source == source for warning in warnings):
            warnings.append(_source_warning_for_stale(source))
    for regulation in regulations:
        if regulation.manual_review_required:
            warnings.append(_manual_review_warning(regulation))
    return warnings


def _manual_review_warnings(regulations: list[Regulation]) -> list[SourceWarning]:
    return [
        _manual_review_warning(regulation)
        for regulation in regulations
        if regulation.manual_review_required
    ]


def _manual_review_warning(regulation: Regulation) -> SourceWarning:
    return SourceWarning(
        source="adfg_emergency_orders",
        severity="critical" if regulation.status == "closed" else "warning",
        user_title="Emergency order needs manual review",
        user_message=(
            f"{regulation.title} is PDF-only or not confidently parsed. "
            "Check the official ADF&G order before relying on legal status."
        ),
        affects_score=True,
        affects_legal_status=True,
    )


def _active_regulations_for_date(
    regulations: list[Regulation],
    generated_at: datetime,
) -> list[Regulation]:
    today = generated_at.date()
    active: list[Regulation] = []
    for regulation in regulations:
        if regulation.effective_date is not None and regulation.effective_date > today:
            continue
        if regulation.expires_date is not None and regulation.expires_date < today:
            continue
        active.append(regulation)
    return active


def _manual_review_alerts(regulations: list[Regulation]) -> list[Alert]:
    alerts: list[Alert] = []
    for regulation in regulations:
        if not regulation.manual_review_required:
            continue
        alerts.append(
            Alert(
                title="Manual review required for ADF&G order",
                severity="warning",
                summary=(
                    f"{regulation.title} is PDF-only or could not be confidently parsed. "
                    "Review the official ADF&G source."
                ),
                source="adfg_emergency_orders",
            )
        )
    return alerts


def _enrich_source_health(
    generated_at: datetime,
    source_health: list[SourceHealth],
) -> list[SourceHealth]:
    return [_enriched_health(generated_at, health) for health in source_health]


def _enriched_health(generated_at: datetime, health: SourceHealth) -> SourceHealth:
    checked_at = health.last_checked_at
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=UTC)
    freshness_minutes = max(0, round((generated_at - checked_at).total_seconds() / 60))
    stale = freshness_minutes > FRESHNESS_LIMIT_HOURS.get(health.source, 24) * 60
    status = health.status
    severity = health.severity
    if status == "ok" and stale:
        status = "degraded"
        severity = "warning"
    elif status == "failed":
        severity = "critical" if _affects_legal_status(health.source) else "warning"
    elif status == "degraded" and severity == "info":
        severity = "watch"
    freshness_status = "stale" if stale else "current"
    if status == "failed" and health.last_success_at is None:
        freshness_status = "missing"
    user_title, user_message = _source_user_copy(health.source, status, stale, health.message)
    return SourceHealth(
        source=health.source,
        status=status,
        severity=severity,
        user_title=health.user_title or user_title,
        user_message=health.user_message or user_message,
        last_checked_at=health.last_checked_at,
        last_success_at=health.last_success_at
        or (health.last_checked_at if status != "failed" else None),
        freshness_minutes=freshness_minutes,
        freshness_status=freshness_status,
        last_error=health.last_error or (health.message if status == "failed" else None),
        affects_score=_affects_score(health.source),
        affects_legal_status=_affects_legal_status(health.source),
        message=health.message,
    )


def _source_user_copy(
    source: str,
    status: str,
    stale: bool,
    message: str,
) -> tuple[str, str]:
    if source == "adfg_emergency_orders":
        if status == "failed":
            return "Regulation source unavailable", message
        return (
            "Regulation source needs attention",
            message if stale else "ADF&G emergency orders checked.",
        )
    if source == "adfg_fish_counts":
        return "Fish count data needs attention", message
    if source == "usgs":
        return "Water data needs attention", message
    if source == "nws":
        return "Weather data needs attention", message
    if source == "noaa_tides":
        return "Tide data needs attention", message
    if source == "usgs_statistics":
        return "Historical flow data needs attention", message
    return f"{source} source needs attention", message


def _source_warning_for_missing(source: str) -> SourceWarning:
    severity = "critical" if _affects_legal_status(source) else "warning"
    title, message = _source_user_copy(
        source,
        "failed",
        False,
        "Required source data is missing from the latest report.",
    )
    return SourceWarning(
        source=source,
        severity=severity,
        user_title=title,
        user_message=message,
        affects_score=_affects_score(source),
        affects_legal_status=_affects_legal_status(source),
    )


def _source_warning_for_stale(source: str) -> SourceWarning:
    title, message = _source_user_copy(source, "degraded", True, "Source data is stale.")
    return SourceWarning(
        source=source,
        severity="warning",
        user_title=title,
        user_message=message,
        affects_score=_affects_score(source),
        affects_legal_status=_affects_legal_status(source),
    )


def _affects_legal_status(source: str) -> bool:
    return source in {"adfg_emergency_orders", "baseline_regulations"}


def _affects_score(source: str) -> bool:
    return source in REQUIRED_SCORE_SOURCES or source == "baseline_regulations"


def _stale_required_sources(
    generated_at: datetime,
    source_health: list[SourceHealth],
) -> list[str]:
    stale_sources: list[str] = []
    for health in source_health:
        if health.source not in _required_score_sources_for_date(generated_at):
            continue
        if health.status == "failed":
            continue
        checked_at = health.last_checked_at
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=UTC)
        limit_hours = FRESHNESS_LIMIT_HOURS.get(health.source, 24)
        age_hours = (generated_at - checked_at).total_seconds() / 3600
        if age_hours > limit_hours:
            stale_sources.append(health.source)
    return sorted(stale_sources)


def _prefix_source_warning(summary: str, source_warning: str) -> str:
    if not source_warning:
        return summary
    return f"{source_warning} {summary}"


def _default_source_health(
    generated_at: datetime,
    observations: list[UsgsObservation],
    active_regulations: list[Regulation],
    active_fish_counts: list[FishCount],
    active_alerts: list[Alert],
    usgs_observations: list[UsgsObservation] | None,
    regulations: list[Regulation] | None,
    fish_counts: list[FishCount] | None,
    alerts: list[Alert] | None,
) -> list[SourceHealth]:
    return _enrich_source_health(
        generated_at,
        [
            _source_health(
                "usgs",
                len(observations),
                "normalized USGS observations",
                generated_at,
                zero_records_are_normalized=usgs_observations is not None,
            ),
            _source_health(
                "adfg_emergency_orders",
                len(active_regulations) if regulations is not None else 0,
                "normalized ADFG emergency orders",
                generated_at,
                zero_records_are_normalized=regulations is not None,
            ),
            _fish_count_source_health(
                generated_at,
                len(active_fish_counts) if fish_counts is not None else 0,
                zero_records_are_normalized=fish_counts is not None,
            ),
            _source_health(
                "nws",
                len(active_alerts) if alerts is not None else 0,
                "normalized NWS alerts",
                generated_at,
                zero_records_are_normalized=alerts is not None,
            ),
        ],
    )


def _required_score_sources_for_date(generated_at: datetime) -> set[str]:
    return {
        source
        for source in REQUIRED_SCORE_SOURCES
        if is_score_source_active(source, generated_at.date())
    }


def _fish_count_source_health(
    generated_at: datetime,
    record_count: int,
    *,
    zero_records_are_normalized: bool,
) -> SourceHealth:
    if is_score_source_active("adfg_fish_counts", generated_at.date()):
        return _source_health(
            "adfg_fish_counts",
            record_count,
            "normalized ADFG fish count records",
            generated_at,
            zero_records_are_normalized=zero_records_are_normalized,
        )
    return SourceHealth(
        source="adfg_fish_counts",
        status="ok",
        severity="info",
        last_checked_at=generated_at,
        message="ADF&G fish count source is outside its active run window.",
    )


def _source_health(
    source: str,
    record_count: int,
    label: str,
    generated_at: datetime,
    *,
    zero_records_are_normalized: bool = False,
) -> SourceHealth:
    has_normalized_data = bool(record_count or zero_records_are_normalized)
    return SourceHealth(
        source=source,
        status="ok" if has_normalized_data else "degraded",
        severity="info" if has_normalized_data else "watch",
        last_checked_at=generated_at,
        message=(
            f"{record_count} {label} available."
            if has_normalized_data
            else f"Adapter available; no {label} are available yet."
        ),
    )
