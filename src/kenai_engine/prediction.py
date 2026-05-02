"""Prototype spot-window predictions.

This module is intentionally additive: it does not replace the v1 report builder
or public JSON contract. It provides a small, explainable foundation for future
v2-style predictions.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from kenai_engine.models import (
    AccessPoint,
    FeatureContribution,
    PredictionSourceState,
    Regulation,
    SourceHealth,
    SourceProvenance,
    SpotWindowPrediction,
)
from kenai_engine.scoring import FRESHNESS_LIMIT_HOURS
from kenai_engine.spatial import load_spatial_catalog, resolve_spot

ADFG_ORDERS_URL = "https://www.adfg.alaska.gov/sf/EONR/"


def assess_prediction_source_state(
    generated_at: datetime,
    source_health: list[SourceHealth],
) -> PredictionSourceState:
    """Summarize source health for conservative prototype predictions."""

    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    if not source_health:
        return PredictionSourceState(
            freshness="missing",
            confidence="low",
            cautions=["Required source health is missing for prototype predictions."],
            missing_sources=["adfg_emergency_orders"],
        )

    health_by_source = {health.source: health for health in source_health}
    cautions: list[str] = []
    stale_sources: list[str] = []
    missing_sources: list[str] = []

    adfg_health = health_by_source.get("adfg_emergency_orders")
    if adfg_health is None:
        missing_sources.append("adfg_emergency_orders")
        cautions.append("ADF&G emergency order source health is missing.")
    elif adfg_health.status == "failed":
        missing_sources.append("adfg_emergency_orders")
        cautions.append("ADF&G emergency order source is unavailable.")
    elif adfg_health.status == "degraded":
        stale_sources.append("adfg_emergency_orders")
        cautions.append("ADF&G emergency order source is degraded.")

    for health in source_health:
        if health.status in {"failed", "degraded"}:
            continue
        checked_at = _as_utc(health.last_checked_at)
        age_hours = (generated_at - checked_at).total_seconds() / 3600
        if age_hours > FRESHNESS_LIMIT_HOURS.get(health.source, 24):
            stale_sources.append(health.source)
    if stale_sources:
        cautions.append(f"Stale source data: {', '.join(sorted(stale_sources))}.")

    if missing_sources:
        freshness = "missing"
    elif stale_sources:
        freshness = "stale"
    else:
        freshness = "fresh"

    confidence = "medium" if freshness == "fresh" else "low"
    return PredictionSourceState(
        freshness=freshness,
        confidence=confidence,
        cautions=cautions,
        stale_sources=sorted(stale_sources),
        missing_sources=sorted(missing_sources),
    )


def build_spot_window_predictions(
    *,
    generated_at: datetime,
    spot_ids: list[str] | None = None,
    target_species: str = "sockeye",
    source_health: list[SourceHealth] | None = None,
    regulations: list[Regulation] | None = None,
    window_hours: int = 6,
) -> list[SpotWindowPrediction]:
    """Build deterministic prototype predictions for selected spots."""

    generated_at = _as_utc(generated_at)
    active_source_health = [] if source_health is None else source_health
    source_state = assess_prediction_source_state(generated_at, active_source_health)
    catalog = load_spatial_catalog()
    selected_spot_ids = spot_ids or [spot.id for spot in catalog.access_points]
    active_regulations = _active_regulations(regulations or [], generated_at)

    predictions: list[SpotWindowPrediction] = []
    for spot_id in selected_spot_ids:
        spot = resolve_spot(spot_id, catalog)
        legal_status, legal_cautions, legal_uncertain = _legal_assessment(active_regulations)
        legal_cautions = [*legal_cautions, *source_state.cautions]
        score_band = "fair"
        condition_score: int | None = 55
        confidence = source_state.confidence
        if legal_uncertain or source_state.confidence == "low":
            confidence = "low"
        if legal_status == "closed":
            score_band = "closed"
            condition_score = 0
        elif legal_uncertain:
            score_band = "unknown"
            condition_score = None

        predictions.append(
            SpotWindowPrediction(
                generated_at=generated_at,
                spot_id=spot.id,
                spot_name=spot.name,
                target_species=target_species,
                window_start=generated_at,
                window_end=generated_at + timedelta(hours=window_hours),
                score_band=score_band,
                condition_score=condition_score,
                confidence=confidence,
                freshness=source_state.freshness,
                legal_status=legal_status,
                safety_status="caution",
                feature_contributions=[_spatial_feature(spot)],
                legal_cautions=legal_cautions or [
                    (
                        "No active closure or restriction was found in prototype inputs, "
                        "but baseline regulations are not fully evaluated here."
                    )
                ],
                safety_cautions=[
                    (
                        "Prototype prediction separates condition quality from legal "
                        "permission and safety."
                    )
                ],
                provenance=[
                    *_spatial_provenance(spot),
                    *_source_health_provenance(generated_at, active_source_health),
                ],
            )
        )
    return predictions


def _legal_assessment(regulations: list[Regulation]) -> tuple[str, list[str], bool]:
    cautions: list[str] = []
    for regulation in regulations:
        if regulation.status == "closed":
            return "closed", [f"{regulation.title} indicates a closure."], True
        if regulation.status == "unknown":
            cautions.append(
                f"{regulation.title} has unknown legal effect; check the official ADF&G order."
            )
        if regulation.manual_review_required:
            cautions.append(
                f"{regulation.title} requires manual review before relying on legal status."
            )
        status = "restricted" if regulation.status == "restricted" else "unknown"
        if cautions:
            return status, cautions, True
    return "unknown", [], False


def _active_regulations(regulations: list[Regulation], generated_at: datetime) -> list[Regulation]:
    today = generated_at.date()
    active: list[Regulation] = []
    for regulation in regulations:
        if regulation.effective_date is not None and regulation.effective_date > today:
            continue
        if regulation.expires_date is not None and regulation.expires_date < today:
            continue
        active.append(regulation)
    return active


def _spatial_feature(spot: AccessPoint) -> FeatureContribution:
    usgs_relevance = [
        relevance for relevance in spot.source_relevance if relevance.source == "usgs"
    ]
    best = max(usgs_relevance, key=lambda item: item.confidence_weight, default=None)
    value = 0.0 if best is None else best.confidence_weight
    return FeatureContribution(
        feature="spatial_relevance",
        value=value,
        weight=1.0,
        direction="positive" if value else "neutral",
        contribution=value,
        explanation=f"{spot.name} has a primary USGS source mapping for this prototype."
        if best and best.role == "primary"
        else f"{spot.name} has limited source mapping for this prototype.",
        source_ids=[f"usgs:{best.source_id}"] if best else [],
    )


def _spatial_provenance(spot: AccessPoint) -> list[SourceProvenance]:
    provenance: list[SourceProvenance] = []
    for relevance in spot.source_relevance:
        if relevance.source != "usgs":
            continue
        provenance.append(
            SourceProvenance(
                source_id=f"usgs:{relevance.source_id}",
                agency="USGS",
                dataset="Kenai River gage relevance",
                freshness="fresh",
                confidence=relevance.confidence_weight,
                notes=f"{relevance.role} source mapping from spatial catalog",
            )
        )
        break
    return provenance


def _source_health_provenance(
    generated_at: datetime,
    source_health: list[SourceHealth],
) -> list[SourceProvenance]:
    provenance: list[SourceProvenance] = []
    for health in source_health:
        if health.source != "adfg_emergency_orders":
            continue
        checked_at = _as_utc(health.last_checked_at)
        freshness = (
            "missing"
            if health.status == "failed"
            else "stale"
            if (generated_at - checked_at).total_seconds() / 3600
            > FRESHNESS_LIMIT_HOURS["adfg_emergency_orders"]
            else "fresh"
        )
        provenance.append(
            SourceProvenance(
                source_id="adfg_emergency_orders",
                agency="ADF&G",
                dataset="Emergency orders source health",
                retrieved_at=checked_at,
                expires_at=checked_at
                + timedelta(hours=FRESHNESS_LIMIT_HOURS["adfg_emergency_orders"]),
                freshness=freshness,
                confidence=0.8 if freshness == "fresh" else 0.25,
                url=ADFG_ORDERS_URL,
                notes=f"Source health status: {health.status}",
            )
        )
    return provenance


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
