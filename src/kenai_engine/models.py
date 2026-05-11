"""Pydantic models for normalized inputs and app-facing reports."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0.0"
ENGINE_NAME = "kenai-condition-engine"
ENGINE_VERSION = "0.1.0"

ConditionStatus = Literal["poor", "fair", "good", "excellent", "restricted", "closed", "unknown"]
RegulationStatus = Literal["open", "restricted", "closed", "unknown"]
SourceStatus = Literal["ok", "degraded", "failed"]
WarningSeverity = Literal["info", "watch", "warning", "critical"]
ReportStatus = Literal["ok", "degraded", "failed"]
ConfidenceBand = Literal["low", "medium", "high"]
SourceFreshnessStatus = Literal["current", "stale", "missing"]
BarometricTrend = Literal["rising", "steady", "falling"]
FloodAlertSeverity = Literal["info", "watch", "warning"]
FishCountTrend = Literal["rising", "steady", "falling", "unknown"]
TideStage = Literal["incoming", "high", "outgoing", "low", "unknown"]
FreshnessStatus = Literal["fresh", "stale", "missing"]
PredictionConfidence = Literal["high", "medium", "low"]
PredictionScoreBand = Literal[
    "poor", "fair", "good", "very_good", "unknown", "closed", "restricted"
]


class LocationCondition(BaseModel):
    """Condition summary for a named Kenai River location."""

    id: str = "kenai_river"
    name: str
    segment: str = "all"
    lat: float | None = None
    lon: float | None = None
    fishing_context: str = ""
    condition_score: int = Field(default=0, ge=0, le=100)
    status: ConditionStatus = "unknown"
    score: int = Field(ge=0, le=100)
    confidence: float = Field(default=0.35, ge=0, le=1)
    water: dict[str, object | None] = Field(default_factory=dict)
    weather: dict[str, object | None] = Field(default_factory=dict)
    alerts: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    bank_fishing_score: int | None = Field(default=None, ge=0, le=100)
    boat_fishing_score: int | None = Field(default=None, ge=0, le=100)
    sockeye_score: int | None = Field(default=None, ge=0, le=100)
    chinook_score: int | None = Field(default=None, ge=0, le=100)
    coho_score: int | None = Field(default=None, ge=0, le=100)
    rainbow_trout_score: int | None = Field(default=None, ge=0, le=100)
    dolly_varden_score: int | None = Field(default=None, ge=0, le=100)
    score_delta_reason: str = ""
    contributing_factors: list[str] = Field(default_factory=list)
    limiting_factors: list[str] = Field(default_factory=list)
    confidence_explanation: str = ""
    legal_explanation: str = ""
    recommended_user_action: str = ""
    component_scores: dict[str, int] = Field(default_factory=dict)
    source_provenance: list[dict[str, object | None]] = Field(default_factory=list)


class SpeciesScore(BaseModel):
    """Species-specific score when supported by current data."""

    species: str
    score: int | None = Field(default=None, ge=0, le=100)
    status: ConditionStatus
    confidence: float = Field(default=0.0, ge=0, le=1)
    explanation: str
    source: str | None = None


class SourceWarning(BaseModel):
    """User-visible warning derived from source health or manual-review requirements."""

    source: str
    severity: WarningSeverity
    user_title: str
    user_message: str
    affects_score: bool = False
    affects_legal_status: bool = False


class Regulation(BaseModel):
    """Current regulatory state as understood by the engine."""

    title: str
    status: RegulationStatus
    effective_date: date | None = None
    expires_date: date | None = None
    source_url: str | None = None
    summary: str
    manual_review_required: bool = False
    content_type: Literal["html", "pdf", "unknown"] = "html"


class BaselineRegulation(BaseModel):
    """Manual-review baseline regulation context separate from emergency orders."""

    id: str
    species: str
    segments: list[str] = Field(default_factory=list)
    season_start: str | None = None
    season_end: str | None = None
    gear_notes: str = ""
    bag_possession_summary: str = ""
    source_url: str
    notes: str = ""
    last_reviewed: date
    review_status: Literal["manual-review", "verified"] = "manual-review"


class FishCount(BaseModel):
    """Fish count observation for a species and location."""

    species: str
    location: str
    count: int = Field(ge=0)
    daily_count: int | None = Field(default=None, ge=0)
    cumulative_count: int | None = Field(default=None, ge=0)
    count_location_id: str | None = None
    species_id: str | None = None
    method: str | None = None
    year: int | None = None
    parser_degraded: bool = False
    manual_review_required: bool = False
    observation_date: date
    source_url: str | None = None


class UsgsObservation(BaseModel):
    """Normalized USGS instantaneous-value observation."""

    site_id: str
    monitoring_location_id: str = ""
    site_name: str
    parameter_code: str
    parameter_name: str
    value: float
    unit: str
    observed_at: datetime
    qualifiers: list[str] = Field(default_factory=list)


class Alert(BaseModel):
    """Weather, river, or operational alert."""

    title: str
    severity: Literal["info", "watch", "warning"]
    summary: str
    source: str


class WeatherObservation(BaseModel):
    """Normalized weather signal for scoring."""

    location: str
    observed_at: datetime
    recent_rain_inches_24h: float | None = Field(default=None, ge=0)
    wind_mph: float | None = Field(default=None, ge=0)
    temperature_f: float | None = None
    wind_direction: str | None = None
    short_forecast: str | None = None
    precipitation_probability: int | None = Field(default=None, ge=0, le=100)
    detailed_forecast: str | None = None
    source: str


class TidePrediction(BaseModel):
    """NOAA tide prediction."""

    station_id: str = "9455742"
    predicted_at: datetime
    height_ft: float
    tide_type: Literal["H", "L"]
    source_url: str | None = None


class UsgsFlowStatistic(BaseModel):
    """USGS day-of-year flow percentiles."""

    site_id: str
    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)
    parameter_code: str = "00060"
    unit: str = ""
    p25: float | None = None
    p50: float | None = None
    p75: float | None = None
    p90: float | None = None
    p95: float | None = None


class SourceHealth(BaseModel):
    """Health and freshness indicator for a source adapter."""

    source: str
    status: SourceStatus
    severity: WarningSeverity = "info"
    user_title: str = ""
    user_message: str = ""
    last_checked_at: datetime
    last_success_at: datetime | None = None
    freshness_minutes: int | None = None
    freshness_status: SourceFreshnessStatus = "missing"
    last_error: str | None = None
    affects_score: bool = False
    affects_legal_status: bool = False
    message: str


class SourceProvenance(BaseModel):
    """Source metadata attached to prototype prediction outputs."""

    source_id: str
    agency: str
    dataset: str
    retrieved_at: datetime | None = None
    observed_at: datetime | None = None
    expires_at: datetime | None = None
    freshness: FreshnessStatus
    confidence: float = Field(ge=0, le=1)
    url: str | None = None
    notes: str = ""


class FeatureContribution(BaseModel):
    """Explainable feature contribution for prototype predictions."""

    feature: str
    value: float = Field(ge=0, le=1)
    weight: float = Field(ge=0, le=1)
    direction: Literal["positive", "negative", "neutral"]
    contribution: float
    explanation: str
    source_ids: list[str] = Field(default_factory=list)


class SourceRelevance(BaseModel):
    """Spatial relationship between an access point and a source."""

    source: str
    source_id: str
    role: Literal["primary", "secondary", "upstream", "downstream", "regional", "marine"]
    applies_to: list[str] = Field(default_factory=list)
    confidence_weight: float = Field(ge=0, le=1)
    distance_miles: float | None = Field(default=None, ge=0)
    river_mile_delta: float | None = None
    notes: str = ""


class AccessPoint(BaseModel):
    """Prototype spatial catalog access point."""

    id: str
    name: str
    segment: str
    lat: float
    lon: float
    river_mile: float | None = None
    access_modes: list[str] = Field(default_factory=list)
    target_species: list[str] = Field(default_factory=list)
    tide_relevance: Literal["none", "low", "medium", "high"] = "none"
    legal_area_ids: list[str] = Field(default_factory=list)
    source_relevance: list[SourceRelevance]


class SpatialCatalog(BaseModel):
    """Versioned spatial catalog used by prototype predictions."""

    schema_version: Literal["1.0.0"]
    access_points: list[AccessPoint] = Field(min_length=1)


class PredictionSourceState(BaseModel):
    """Summarized source-health state for prototype predictions."""

    freshness: FreshnessStatus
    confidence: PredictionConfidence
    cautions: list[str] = Field(default_factory=list)
    stale_sources: list[str] = Field(default_factory=list)
    missing_sources: list[str] = Field(default_factory=list)


class SpotWindowPrediction(BaseModel):
    """Prototype v2-style spot/time-window prediction."""

    schema_version: Literal["prediction-prototype-0.1"] = "prediction-prototype-0.1"
    generated_at: datetime
    spot_id: str
    spot_name: str
    target_species: str
    window_start: datetime
    window_end: datetime
    score_band: PredictionScoreBand
    condition_score: int | None = Field(default=None, ge=0, le=100)
    confidence: PredictionConfidence
    freshness: FreshnessStatus
    legal_status: RegulationStatus
    safety_status: Literal["normal", "caution", "hazard"] = "caution"
    feature_contributions: list[FeatureContribution] = Field(default_factory=list)
    legal_cautions: list[str] = Field(default_factory=list)
    safety_cautions: list[str] = Field(default_factory=list)
    provenance: list[SourceProvenance] = Field(default_factory=list)


class ScoreInput(BaseModel):
    """Normalized inputs used by the deterministic scoring module."""

    base_score: int = Field(default=72, ge=0, le=100)
    active_closure: bool = False
    active_restriction: bool = False
    legal_uncertainty: bool = False
    confidence: float = Field(default=0.35, ge=0, le=1)
    location: str | None = None
    species: str | None = None
    water_temperature_f: float | None = None
    flow_percentile: float | None = Field(default=None, ge=0, le=100)
    gage_height_trend_ft_24h: float | None = None
    recent_rain_inches_24h: float | None = Field(default=None, ge=0)
    wind_mph: float | None = Field(default=None, ge=0)
    barometric_pressure_inhg: float | None = None
    barometric_trend: BarometricTrend | None = None
    tide_stage: TideStage | None = None
    fish_count_3day_avg: int | None = Field(default=None, ge=0)
    fish_count_trend: FishCountTrend = "unknown"
    flood_alert_active: bool = False
    flood_alert_severity: FloodAlertSeverity = "info"
    source_freshness_hours: dict[str, float] = Field(default_factory=dict)
    missing_sources: list[str] = Field(default_factory=list)


class ScoreResult(BaseModel):
    """Computed score and status."""

    overall_score: int = Field(ge=0, le=100)
    overall_status: ConditionStatus
    confidence: float = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)
    legal_status: RegulationStatus = "open"
    source_freshness_status: Literal["fresh", "stale", "missing"] = "missing"
    location_scores: dict[str, int] = Field(default_factory=dict)
    species_scores: dict[str, int] = Field(default_factory=dict)
    score_delta_reason: str = ""
    contributing_factors: list[str] = Field(default_factory=list)
    limiting_factors: list[str] = Field(default_factory=list)
    confidence_explanation: str = ""
    legal_explanation: str = ""
    recommended_user_action: str = ""


class Report(BaseModel):
    """App-facing latest report."""

    model_config = ConfigDict(use_enum_values=True)

    schema_version: Literal["1.0.0"]
    engine_version: str = ENGINE_VERSION
    generated_by: str = ENGINE_NAME
    report_date: date
    generated_at: datetime
    expires_at: datetime
    report_status: ReportStatus
    river: str
    overall_score: int = Field(ge=0, le=100)
    overall_status: ConditionStatus
    confidence: float = Field(ge=0, le=1)
    confidence_band: ConfidenceBand
    summary: str
    locations: list[LocationCondition]
    species_scores: list[SpeciesScore] = Field(default_factory=list)
    baseline_regulations: list[BaselineRegulation] = Field(default_factory=list)
    emergency_orders: list[Regulation] = Field(default_factory=list)
    regulations: list[Regulation]
    fish_counts: list[FishCount]
    alerts: list[Alert]
    warnings: list[SourceWarning] = Field(default_factory=list)
    source_health: list[SourceHealth]
