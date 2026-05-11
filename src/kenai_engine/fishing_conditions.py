"""Pure fishing-condition prediction engine.

The functions here are deterministic and offline-safe: callers pass already
fetched/normalized records, and the engine returns score, confidence, freshness,
and cautious explanation copy without making legal or safety claims.
"""

from __future__ import annotations

import csv
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from kenai_engine.models import SourceHealth, TidePrediction
from kenai_engine.scoring import FRESHNESS_LIMIT_HOURS
from kenai_engine.sources.noaa_tides import determine_tide_stage

DEFAULT_HISTORICAL_SOCKEYE_PATH = Path("data/config/historical_sockeye_run_timing.csv")

Rating = Literal["Poor", "Fair", "Good", "Excellent"]
Confidence = Literal["Low", "Medium", "High"]
FreshnessLabel = Literal["fresh", "stale", "missing", "cached", "malformed"]
Trend = Literal["rising", "falling", "stable", "unknown"]
TidePhase = Literal["incoming", "outgoing", "slack_high", "slack_low", "unknown"]
Direction = Literal["positive", "negative", "neutral"]

OFFICIAL_SOURCE_REMINDER = (
    "Planning signal only. Check official ADF&G regulations, emergency orders, "
    "USGS/NWS conditions, and local access information before fishing."
)


class DataFreshness(BaseModel):
    source: str
    status: FreshnessLabel = "fresh"
    age_hours: float | None = Field(default=None, ge=0)
    label: str = ""


class HydrologySnapshot(BaseModel):
    flow_cfs: float | None = Field(default=None, ge=0)
    flow_percentile: float | None = Field(default=None, ge=0, le=100)
    flow_trend: Trend = "unknown"
    gauge_height_ft: float | None = None
    water_temp_f: float | None = None
    water_temp_trend: Trend = "unknown"
    turbidity_fnu: float | None = Field(default=None, ge=0)
    recent_rain_inches_24h: float | None = Field(default=None, ge=0)


class TideSnapshot(BaseModel):
    phase: TidePhase = "unknown"
    height_ft: float | None = None
    height_delta_ft: float | None = None
    hours_until_high: float | None = Field(default=None, ge=0)
    hours_until_low: float | None = Field(default=None, ge=0)
    cycle_position: float | None = Field(default=None, ge=0, le=1)
    movement_strength: float | None = Field(default=None, ge=0, le=1)
    access_tide_relevance: Literal["none", "low", "medium", "high"] = "high"


class WeatherSnapshot(BaseModel):
    air_temp_f: float | None = None
    wind_mph: float | None = Field(default=None, ge=0)
    wind_direction: str | None = None
    pressure_trend: Trend = "unknown"
    precipitation_inches_24h: float | None = Field(default=None, ge=0)
    cloud_cover_percent: float | None = Field(default=None, ge=0, le=100)
    storm_signal: bool = False
    severe_weather_signal: bool = False


class BiologicalSignal(BaseModel):
    species: str = "sockeye"
    run_phase: Literal["Pre-Peak", "Peak", "Post-Peak", "Unknown"] = "Unknown"
    run_timing_percentile: float | None = Field(default=None, ge=0, le=1)
    fish_count_trend: Literal["improving", "declining", "stable", "unknown"] = "unknown"
    pulse_strength: float | None = Field(default=None, ge=-1, le=1)
    seven_day_avg: int | None = Field(default=None, ge=0)
    historical_only: bool = False


class AccessConditionSignal(BaseModel):
    access_id: str | None = None
    selected_access_id: str | None = None
    tide_relevance: Literal["none", "low", "medium", "high"] = "none"
    source_degraded: bool = False
    match_confidence: float = Field(default=0.5, ge=0, le=1)
    stage_fit: float | None = Field(default=None, ge=0, le=1)


class FishingConditionFactor(BaseModel):
    name: str
    direction: Direction
    contribution: float
    explanation: str
    source: str | None = None


class FishingConditionInput(BaseModel):
    generated_at: datetime
    target_species: str = "sockeye"
    access_id: str | None = None
    hydrology: HydrologySnapshot | None = None
    tide: TideSnapshot | None = None
    weather: WeatherSnapshot | None = None
    biological: BiologicalSignal | None = None
    access: AccessConditionSignal | None = None
    data_freshness: list[DataFreshness] | None = None
    source_health: list[SourceHealth] = Field(default_factory=list)


class FishingConditionResult(BaseModel):
    score: int = Field(ge=0, le=100)
    rating: Rating
    confidence: Confidence
    confidenceScore: float = Field(ge=0, le=1)
    topPositiveFactors: list[FishingConditionFactor]
    topNegativeFactors: list[FishingConditionFactor]
    dataFreshnessSummary: str
    officialSourceReminder: str = OFFICIAL_SOURCE_REMINDER
    componentScores: dict[str, int]


def score_fishing_conditions(condition_input: FishingConditionInput) -> FishingConditionResult:
    factors: list[FishingConditionFactor] = []
    components = {
        "hydrology": _hydrology_score(condition_input.hydrology, factors),
        "tide": _tide_score(condition_input.tide, condition_input.access, factors),
        "weather": _weather_score(condition_input.weather, factors),
        "seasonal_biological": _biological_score(condition_input.biological, factors),
        "recent_activity": _activity_score(condition_input.biological, factors),
        "access": _access_score(condition_input.access, factors),
    }
    weights = {
        "hydrology": 0.25,
        "tide": 0.20,
        "weather": 0.15,
        "seasonal_biological": 0.20,
        "recent_activity": 0.10,
        "access": 0.10,
    }
    raw_score = sum(components[name] * weight for name, weight in weights.items())
    freshness = condition_input.data_freshness or _freshness_from_health(
        condition_input.generated_at,
        condition_input.source_health,
    )
    confidence_score, quality_multiplier, freshness_summary = _confidence_and_quality(freshness)
    score = _clamp(round(raw_score * quality_multiplier))
    positives = sorted(
        [factor for factor in factors if factor.direction == "positive"],
        key=lambda factor: factor.contribution,
        reverse=True,
    )[:4]
    negatives = sorted(
        [factor for factor in factors if factor.direction == "negative"],
        key=lambda factor: abs(factor.contribution),
        reverse=True,
    )[:4]
    return FishingConditionResult(
        score=score,
        rating=_rating(score),
        confidence=_confidence_band(confidence_score),
        confidenceScore=round(confidence_score, 2),
        topPositiveFactors=positives,
        topNegativeFactors=negatives,
        dataFreshnessSummary=freshness_summary,
        componentScores={name: _clamp(value) for name, value in components.items()},
    )


def extract_tide_snapshot(
    predictions: list[TidePrediction],
    generated_at: datetime,
    *,
    access_tide_relevance: Literal["none", "low", "medium", "high"] = "high",
) -> TideSnapshot | None:
    if not predictions:
        return None
    stage = determine_tide_stage(predictions, generated_at)
    ordered = sorted(predictions, key=lambda prediction: prediction.predicted_at)
    previous = next((item for item in reversed(ordered) if item.predicted_at <= generated_at), None)
    next_high = next(
        (item for item in ordered if item.predicted_at > generated_at and item.tide_type == "H"),
        None,
    )
    next_low = next(
        (item for item in ordered if item.predicted_at > generated_at and item.tide_type == "L"),
        None,
    )
    next_any = next((item for item in ordered if item.predicted_at > generated_at), None)
    phase = {
        "incoming": "incoming",
        "outgoing": "outgoing",
        "high": "slack_high",
        "low": "slack_low",
    }.get(stage, "unknown")
    delta = (
        None
        if previous is None or next_any is None
        else abs(next_any.height_ft - previous.height_ft)
    )
    hours_high = (
        None
        if next_high is None
        else round((next_high.predicted_at - generated_at).total_seconds() / 3600, 2)
    )
    hours_low = (
        None
        if next_low is None
        else round((next_low.predicted_at - generated_at).total_seconds() / 3600, 2)
    )
    movement = None if delta is None else min(1.0, delta / 20)
    return TideSnapshot(
        phase=phase,
        height_ft=previous.height_ft if previous else None,
        height_delta_ft=delta,
        hours_until_high=hours_high,
        hours_until_low=hours_low,
        movement_strength=movement,
        access_tide_relevance=access_tide_relevance,
    )


def sockeye_run_context_for_date(
    target_date: date,
    *,
    path: Path = DEFAULT_HISTORICAL_SOCKEYE_PATH,
) -> BiologicalSignal | None:
    """Return nearest user-provided historical sockeye timing context."""

    if not path.exists():
        return None
    rows = _load_historical_sockeye_rows(path)
    if not rows:
        return None
    target_day = target_date.timetuple().tm_yday
    late_rows = [row for row in rows if row["Run"].lower() == "late"]
    candidates = late_rows or rows
    nearest = min(candidates, key=lambda row: abs(int(row["DayOfYear"]) - target_day))
    trend = "stable"
    pulse = float(nearest["PulseStrength"])
    if pulse >= 0.25:
        trend = "improving"
    elif pulse <= -0.20:
        trend = "declining"
    return BiologicalSignal(
        species="sockeye",
        run_phase=nearest["RunPhase"],
        run_timing_percentile=float(nearest["RunTimingPercentile"]),
        fish_count_trend=trend,
        pulse_strength=pulse,
        seven_day_avg=int(float(nearest["7DayAvg"])),
        historical_only=True,
    )


def _load_historical_sockeye_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [
            row
            for row in csv.DictReader(handle)
            if row.get("Species", "").lower() == "sockeye" and row.get("DayOfYear")
        ]


def _hydrology_score(
    snapshot: HydrologySnapshot | None, factors: list[FishingConditionFactor]
) -> int:
    score = 50
    if snapshot is None:
        _factor(
            factors,
            "hydrology",
            "negative",
            -8,
            "Missing hydrology data reduces confidence in water-condition fit.",
            "usgs",
        )
        return 42
    if snapshot.flow_percentile is not None:
        if 35 <= snapshot.flow_percentile <= 75:
            score += 16
            _factor(
                factors,
                "flow",
                "positive",
                16,
                "Flow is near the normal fishable range for the date.",
                "usgs",
            )
        elif snapshot.flow_percentile >= 90:
            score -= 22
            _factor(
                factors,
                "flow",
                "negative",
                -22,
                "High flow can reduce practical access and water clarity.",
                "usgs",
            )
        elif snapshot.flow_percentile < 15:
            score -= 12
            _factor(
                factors,
                "flow",
                "negative",
                -12,
                "Very low flow can reduce movement lanes and access.",
                "usgs",
            )
    if snapshot.flow_trend == "stable":
        score += 6
    elif snapshot.flow_trend == "rising":
        score -= 10
        _factor(
            factors,
            "flow_trend",
            "negative",
            -10,
            "Rising flow is treated as a clarity and access caution.",
            "usgs",
        )
    elif snapshot.flow_trend == "falling":
        score += 4
    if snapshot.water_temp_f is not None:
        if 45 <= snapshot.water_temp_f <= 58:
            score += 12
            _factor(
                factors,
                "water_temperature",
                "positive",
                12,
                "Water temperature is in a favorable salmonid activity band.",
                "usgs",
            )
        elif snapshot.water_temp_f > 62:
            score -= 16
            _factor(
                factors,
                "water_temperature",
                "negative",
                -16,
                "Warm water lowers the condition signal and can stress fish.",
                "usgs",
            )
    if snapshot.turbidity_fnu is not None and snapshot.turbidity_fnu > 50:
        score -= 10
        _factor(
            factors,
            "clarity",
            "negative",
            -10,
            "High turbidity lowers visibility-sensitive fishing conditions.",
            "usgs",
        )
    if snapshot.recent_rain_inches_24h is not None and snapshot.recent_rain_inches_24h >= 0.75:
        score -= 8
    return _clamp(score)


def _tide_score(
    snapshot: TideSnapshot | None,
    access: AccessConditionSignal | None,
    factors: list[FishingConditionFactor],
) -> int:
    relevance = access.tide_relevance if access else "high"
    if relevance == "none":
        return 50
    if snapshot is None:
        _factor(
            factors,
            "tide",
            "negative",
            -8,
            "Missing tide data; lower-river timing is uncertain.",
            "noaa_tides",
        )
        return 42
    score = 50
    if snapshot.phase == "incoming":
        score += 18
        _factor(
            factors,
            "tide",
            "positive",
            18,
            "Incoming tide is a favorable lower-river timing signal.",
            "noaa_tides",
        )
    elif snapshot.phase == "outgoing":
        score -= 6
        _factor(
            factors,
            "tide",
            "negative",
            -6,
            "Outgoing tide is less favorable for this lower-river planning model.",
            "noaa_tides",
        )
    elif snapshot.phase in {"slack_high", "slack_low"}:
        score -= 12
        _factor(
            factors,
            "tide",
            "negative",
            -12,
            "Slack tide can reduce movement cues near the mouth.",
            "noaa_tides",
        )
    if snapshot.movement_strength is not None and snapshot.movement_strength >= 0.6:
        score += 5
    return _clamp(score)


def _weather_score(snapshot: WeatherSnapshot | None, factors: list[FishingConditionFactor]) -> int:
    if snapshot is None:
        _factor(
            factors,
            "weather",
            "negative",
            -5,
            "Missing weather data leaves wind and rain uncertainty.",
            "nws",
        )
        return 45
    score = 50
    if snapshot.wind_mph is not None:
        if snapshot.wind_mph <= 10:
            score += 8
        elif snapshot.wind_mph >= 20:
            score -= 12
            _factor(
                factors,
                "wind",
                "negative",
                -12,
                "High wind reduces casting and boating practicality.",
                "nws",
            )
    if snapshot.precipitation_inches_24h is not None and snapshot.precipitation_inches_24h >= 0.75:
        score -= 10
        _factor(
            factors, "rain", "negative", -10, "Recent rain is a runoff and clarity caution.", "nws"
        )
    if snapshot.pressure_trend == "stable":
        score += 3
    elif snapshot.pressure_trend == "falling":
        score -= 4
    if snapshot.storm_signal or snapshot.severe_weather_signal:
        score -= 18
        _factor(
            factors,
            "weather_alert",
            "negative",
            -18,
            "Weather signals require conservative planning and NWS checks.",
            "nws",
        )
    return _clamp(score)


def _biological_score(
    snapshot: BiologicalSignal | None, factors: list[FishingConditionFactor]
) -> int:
    if snapshot is None:
        _factor(
            factors,
            "seasonal",
            "negative",
            -5,
            "No biological or seasonal signal is available.",
            "adfg_fish_counts",
        )
        return 45
    score = 50
    if snapshot.run_phase == "Peak":
        score += 15
        _factor(
            factors,
            "run_timing",
            "positive",
            15,
            "Historical run timing suggests a peak seasonal window.",
            "adfg_fish_counts",
        )
    elif snapshot.run_phase == "Pre-Peak":
        score += 6
    elif snapshot.run_phase == "Post-Peak":
        score -= 6
    if snapshot.fish_count_trend == "improving":
        score += 12
        _factor(
            factors,
            "fish_count_trend",
            "positive",
            12,
            "Recent fish-count direction is improving; this is not a catch guarantee.",
            "adfg_fish_counts",
        )
    elif snapshot.fish_count_trend == "declining":
        score -= 10
    if snapshot.pulse_strength is not None:
        if snapshot.pulse_strength >= 0.5:
            score += 10
        elif snapshot.pulse_strength <= -0.3:
            score -= 8
    if snapshot.historical_only:
        score -= 5
        _factor(
            factors,
            "historical_only",
            "negative",
            -5,
            "Using historical-only biological context; live count confidence is lower.",
            "adfg_fish_counts",
        )
    return _clamp(score)


def _activity_score(
    snapshot: BiologicalSignal | None, factors: list[FishingConditionFactor]
) -> int:
    if snapshot and snapshot.seven_day_avg is not None:
        if snapshot.seven_day_avg >= 30_000:
            _factor(
                factors,
                "recent_activity",
                "positive",
                10,
                "Seven-day fish-count average supports a stronger recent activity signal.",
                "adfg_fish_counts",
            )
            return 65
        if snapshot.seven_day_avg < 2_000:
            return 38
    return 50


def _access_score(
    access: AccessConditionSignal | None, factors: list[FishingConditionFactor]
) -> int:
    if access is None:
        _factor(
            factors,
            "access",
            "negative",
            -6,
            "No selected access signal; using general-area fallback.",
            None,
        )
        return 44
    score = 50
    if access.selected_access_id and access.access_id == access.selected_access_id:
        score += round(15 * access.match_confidence)
        _factor(
            factors,
            "access_match",
            "positive",
            8,
            "Selected access matches the condition signal area.",
            None,
        )
    elif access.selected_access_id:
        score -= 10
        _factor(
            factors,
            "access_match",
            "negative",
            -10,
            "Condition signal is a general-area fallback for the selected access.",
            None,
        )
    if access.stage_fit is not None:
        score += round((access.stage_fit - 0.5) * 20)
    if access.source_degraded:
        score -= 8
    return _clamp(score)


def _freshness_from_health(
    generated_at: datetime, source_health: list[SourceHealth]
) -> list[DataFreshness]:
    freshness: list[DataFreshness] = []
    for health in source_health:
        checked_at = health.last_checked_at
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=UTC)
        age_hours = max(0.0, (generated_at - checked_at).total_seconds() / 3600)
        limit = FRESHNESS_LIMIT_HOURS.get(health.source, 24)
        if health.status == "failed":
            status: FreshnessLabel = "missing"
        elif health.status == "degraded" or health.freshness_status == "stale":
            status = "cached"
        elif age_hours > limit:
            status = "stale"
        else:
            status = "fresh"
        freshness.append(DataFreshness(source=health.source, status=status, age_hours=age_hours))
    return freshness


def _confidence_and_quality(freshness: list[DataFreshness]) -> tuple[float, float, str]:
    if not freshness:
        return 0.45, 0.96, "No source freshness metadata supplied; confidence is reduced."
    confidence = 0.82
    multiplier = 1.0
    by_status: dict[str, list[str]] = {}
    for item in freshness:
        by_status.setdefault(item.status, []).append(item.source)
        if item.status == "fresh":
            continue
        if item.status == "stale":
            confidence -= 0.25
            multiplier -= 0.04
        elif item.status == "cached":
            confidence -= 0.30
            multiplier -= 0.06
        elif item.status == "missing":
            confidence -= 0.18
            multiplier -= 0.08
        elif item.status == "malformed":
            confidence -= 0.22
            multiplier -= 0.10
    pieces = [
        f"{status}: {', '.join(sorted(sources))}" for status, sources in sorted(by_status.items())
    ]
    summary = "; ".join(pieces).replace("cached: ", "cached/stale: ")
    return max(0.05, confidence), max(0.65, multiplier), summary


def _factor(
    factors: list[FishingConditionFactor],
    name: str,
    direction: Direction,
    contribution: float,
    explanation: str,
    source: str | None,
) -> None:
    factors.append(
        FishingConditionFactor(
            name=name,
            direction=direction,
            contribution=contribution,
            explanation=explanation,
            source=source,
        )
    )


def _rating(score: int) -> Rating:
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 40:
        return "Fair"
    return "Poor"


def _confidence_band(confidence: float) -> Confidence:
    if confidence >= 0.72:
        return "High"
    if confidence >= 0.60:
        return "Medium"
    return "Low"


def _clamp(value: float) -> int:
    return max(0, min(100, round(value)))
