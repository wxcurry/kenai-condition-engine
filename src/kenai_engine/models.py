"""Pydantic models for normalized inputs and app-facing reports."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ConditionStatus = Literal["good", "caution", "restricted", "closed", "unknown"]
RegulationStatus = Literal["open", "restricted", "closed"]
SourceStatus = Literal["ok", "placeholder", "error"]


class LocationCondition(BaseModel):
    """Condition summary for a named Kenai River location."""

    name: str
    status: ConditionStatus = "unknown"
    score: int = Field(ge=0, le=100)
    notes: list[str] = Field(default_factory=list)


class Regulation(BaseModel):
    """Current regulatory state as understood by the engine."""

    title: str
    status: RegulationStatus
    effective_date: date | None = None
    expires_date: date | None = None
    source_url: str | None = None
    summary: str


class FishCount(BaseModel):
    """Fish count observation for a species and location."""

    species: str
    location: str
    count: int = Field(ge=0)
    observation_date: date
    source_url: str | None = None


class UsgsObservation(BaseModel):
    """Normalized USGS instantaneous-value observation."""

    site_id: str
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


class SourceHealth(BaseModel):
    """Health and freshness indicator for a source adapter."""

    source: str
    status: SourceStatus
    last_checked_at: datetime
    message: str


class ScoreInput(BaseModel):
    """Normalized inputs used by the deterministic scoring module."""

    base_score: int = Field(default=72, ge=0, le=100)
    active_closure: bool = False
    active_restriction: bool = False
    confidence: float = Field(default=0.35, ge=0, le=1)


class ScoreResult(BaseModel):
    """Computed score and status."""

    overall_score: int = Field(ge=0, le=100)
    overall_status: ConditionStatus
    confidence: float = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)


class Report(BaseModel):
    """App-facing latest report."""

    model_config = ConfigDict(use_enum_values=True)

    report_date: date
    generated_at: datetime
    river: str
    overall_score: int = Field(ge=0, le=100)
    overall_status: ConditionStatus
    confidence: float = Field(ge=0, le=1)
    summary: str
    locations: list[LocationCondition]
    regulations: list[Regulation]
    fish_counts: list[FishCount]
    alerts: list[Alert]
    source_health: list[SourceHealth]
