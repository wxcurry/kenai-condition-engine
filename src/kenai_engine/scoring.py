"""Deterministic production scoring rules."""

from __future__ import annotations

from kenai_engine.models import ScoreInput, ScoreResult

KNOWN_LOCATIONS = ("upper_kenai", "middle_kenai", "soldotna", "lower_kenai")
KNOWN_SPECIES = ("sockeye", "chinook", "coho", "rainbow_trout", "dolly_varden")
FRESHNESS_LIMIT_HOURS = {
    "usgs": 6,
    "usgs_statistics": 168,
    "nws": 3,
    "adfg_emergency_orders": 24,
    "adfg_fish_counts": 36,
    "noaa_tides": 24,
}


def score_conditions(score_input: ScoreInput) -> ScoreResult:
    """Score conditions with regulatory overrides first."""

    reasons: list[str] = []
    confidence, source_freshness_status = _score_confidence(score_input, reasons)

    if score_input.active_closure:
        reasons.append("Active closure overrides all other condition signals.")
        return ScoreResult(
            overall_score=0,
            overall_status="closed",
            confidence=confidence,
            reasons=reasons,
            legal_status="closed",
            source_freshness_status=source_freshness_status,
            score_delta_reason="Legal closure forced the score to zero.",
            contributing_factors=[],
            limiting_factors=reasons,
            confidence_explanation=_confidence_explanation(score_input, confidence),
            legal_explanation="An active closure has highest priority over fishing quality.",
            recommended_user_action=(
                "Do not fish this affected fishery; check the official ADF&G order."
            ),
        )

    environmental_score = _environmental_score(score_input, reasons)
    location_scores = _location_scores(score_input, environmental_score)
    species_scores = _species_scores(score_input, environmental_score)
    selected_location_score = location_scores.get(score_input.location or "", environmental_score)
    selected_species_score = species_scores.get(score_input.species or "", environmental_score)
    computed_score = round(
        environmental_score * 0.50 + selected_location_score * 0.25 + selected_species_score * 0.25
    )

    if score_input.active_restriction:
        reasons.append("Active restriction overrides baseline condition status.")
        restricted_confidence = (
            min(confidence, 0.45) if score_input.legal_uncertainty else confidence
        )
        return ScoreResult(
            overall_score=min(computed_score, 45),
            overall_status="restricted",
            confidence=restricted_confidence,
            reasons=reasons,
            legal_status="restricted",
            source_freshness_status=source_freshness_status,
            location_scores=location_scores,
            species_scores=species_scores,
            score_delta_reason="Active restriction capped the condition score.",
            contributing_factors=_positive_reasons(reasons),
            limiting_factors=_limiting_reasons(reasons),
            confidence_explanation=_confidence_explanation(score_input, restricted_confidence),
            legal_explanation=(
                _legal_uncertainty_explanation()
                if score_input.legal_uncertainty
                else "An active restriction overrides normal opportunity scoring."
            ),
            recommended_user_action=_legal_uncertainty_action()
            if score_input.legal_uncertainty
            else "Read the official ADF&G restriction before choosing gear or harvest plans.",
        )

    if score_input.legal_uncertainty:
        reasons.append("Legal status is uncertain because an active order needs manual review.")
        uncertain_score = min(computed_score, 45)
        uncertain_confidence = min(confidence, 0.45)
        return ScoreResult(
            overall_score=uncertain_score,
            overall_status="unknown",
            confidence=uncertain_confidence,
            reasons=reasons,
            legal_status="unknown",
            source_freshness_status=source_freshness_status,
            location_scores=location_scores,
            species_scores=species_scores,
            score_delta_reason="Legal uncertainty capped the condition score.",
            contributing_factors=_positive_reasons(reasons),
            limiting_factors=_limiting_reasons(reasons),
            confidence_explanation=_confidence_explanation(score_input, uncertain_confidence),
            legal_explanation=_legal_uncertainty_explanation(),
            recommended_user_action=_legal_uncertainty_action(),
        )

    if computed_score >= 85:
        status = "excellent"
    elif computed_score >= 70:
        status = "good"
    elif computed_score >= 40 or score_input.flood_alert_active:
        status = "fair"
    else:
        status = "poor"

    reasons.append("No active regulatory override found; using deterministic condition signals.")
    return ScoreResult(
        overall_score=max(0, min(100, computed_score)),
        overall_status=status,
        confidence=confidence,
        reasons=reasons,
        legal_status="open",
        source_freshness_status=source_freshness_status,
        location_scores=location_scores,
        species_scores=species_scores,
        score_delta_reason=_score_delta_reason(computed_score),
        contributing_factors=_positive_reasons(reasons),
        limiting_factors=_limiting_reasons(reasons),
        confidence_explanation=_confidence_explanation(score_input, confidence),
        legal_explanation="No active closure or restriction was found in normalized records.",
        recommended_user_action=_recommended_user_action(status, score_input),
    )


def _environmental_score(score_input: ScoreInput, reasons: list[str]) -> int:
    score = float(score_input.base_score)

    if score_input.water_temperature_f is not None:
        temp = score_input.water_temperature_f
        if 42 <= temp <= 55:
            score += 10
            reasons.append("Water temperature is in the primary salmonid comfort band.")
        elif 38 <= temp < 42:
            score += 2
        elif 55 < temp <= 58:
            score += 4
        elif 58 < temp <= 62:
            score -= 6
            reasons.append("Water temperature is warm enough to reduce catchability.")
        elif 62 < temp <= 64.4:
            score -= 12
            reasons.append("Water temperature is approaching Pacific salmon heat-stress levels.")
        elif temp > 64.4:
            score -= 24
            reasons.append("Water temperature exceeds a Pacific salmon heat-stress threshold.")
        elif temp < 38:
            score -= 8
            reasons.append("Cold water can slow fish movement and feeding.")

    if score_input.air_temperature_f is not None:
        air_temp = score_input.air_temperature_f
        if 45 <= air_temp <= 65:
            score += 2
        elif 25 <= air_temp < 33:
            score -= 3
            reasons.append("Cold air reduces angler comfort and practical fishing quality.")
        elif air_temp < 25:
            score -= 6
            reasons.append("Very cold air reduces angler safety and practical fishing quality.")
        elif air_temp > 75:
            score -= 4
            reasons.append("Hot air can increase fish stress and reduce practical fishing quality.")

    if score_input.precipitation_probability is not None:
        probability = score_input.precipitation_probability
        if probability >= 75:
            score -= 4
            reasons.append("High rain probability increases weather and clarity risk.")
        elif probability >= 50:
            score -= 2
            reasons.append("Rain probability creates some weather and clarity uncertainty.")

    if score_input.recent_rain_inches_24h is not None:
        rain = score_input.recent_rain_inches_24h
        if rain <= 0.10:
            score += 3
        elif rain <= 0.35:
            score += 1
        elif rain < 0.75:
            score -= 4
            reasons.append("Recent rain can reduce clarity and change flows.")
        elif rain <= 1.25:
            score -= 10
            reasons.append("Recent heavy rain can raise flows and reduce clarity.")
        else:
            score -= 16
            reasons.append("Very heavy rain can sharply reduce clarity, access, and safety.")

    if score_input.flow_percentile is not None:
        flow = score_input.flow_percentile
        if 35 <= flow <= 75:
            score += 8
            reasons.append("Flow is near the normal fishable range for the date.")
        elif 85 <= flow < 95:
            score -= 12
            reasons.append("High flow can reduce bank access and visibility.")
        elif flow >= 95:
            score -= 25
            reasons.append("Dangerously high flow lowers safety and fishability.")
        elif flow < 15:
            score -= 10
            reasons.append("Very low flow can reduce movement lanes and boat access.")

    if score_input.gage_height_trend_ft_24h is not None:
        trend = score_input.gage_height_trend_ft_24h
        if abs(trend) <= 0.25:
            score += 4
        elif trend > 0.75:
            score -= 8
            reasons.append("Rapidly rising stage can reduce clarity and safe access.")

    if score_input.wind_mph is not None:
        wind = score_input.wind_mph
        if wind <= 8:
            score += 3
        elif wind <= 15:
            score += 1
        elif wind < 22:
            score -= 3
            reasons.append("Moderate wind can reduce casting and boat control.")
        elif wind <= 30:
            score -= 9
            reasons.append("High wind lowers boating and casting quality.")
        else:
            score -= 16
            reasons.append("Strong wind creates poor boating and casting conditions.")

    if score_input.barometric_trend == "steady":
        score += 2
    elif score_input.barometric_trend == "falling":
        if score_input.flood_alert_active or (
            score_input.recent_rain_inches_24h is not None
            and score_input.recent_rain_inches_24h >= 0.75
        ):
            score -= 4
            reasons.append("Falling pressure paired with heavy rain increases weather risk.")
        else:
            score += 2

    if score_input.flood_alert_active:
        penalty = 18 if score_input.flood_alert_severity == "warning" else 10
        score -= penalty
        reasons.append("NWS or river flood alert is active; safety overrides fishing quality.")

    return max(0, min(100, round(score)))


def _location_scores(score_input: ScoreInput, environmental_score: int) -> dict[str, int]:
    scores = {location: environmental_score for location in KNOWN_LOCATIONS}
    if score_input.tide_stage == "incoming":
        scores["lower_kenai"] += 8
    elif score_input.tide_stage == "outgoing":
        scores["lower_kenai"] -= 5

    if score_input.flow_percentile is not None and score_input.flow_percentile >= 90:
        scores["upper_kenai"] -= 8
        scores["middle_kenai"] -= 12
        scores["soldotna"] -= 10
        scores["lower_kenai"] -= 8

    return {key: max(0, min(100, round(value))) for key, value in scores.items()}


def _species_scores(score_input: ScoreInput, environmental_score: int) -> dict[str, int]:
    scores = {species: environmental_score for species in KNOWN_SPECIES}

    if score_input.fish_count_3day_avg is not None:
        avg = score_input.fish_count_3day_avg
        if avg >= 30_000:
            scores["sockeye"] += 15
        elif avg >= 10_000:
            scores["sockeye"] += 8
        elif avg < 2_000:
            scores["sockeye"] -= 10

    if score_input.fish_count_trend == "rising":
        scores["sockeye"] += 6
        scores["coho"] += 3
    elif score_input.fish_count_trend == "falling":
        scores["sockeye"] -= 6

    if score_input.tide_stage == "incoming":
        scores["coho"] += 6
        scores["chinook"] += 4

    if score_input.water_temperature_f is not None and score_input.water_temperature_f > 62:
        scores["rainbow_trout"] -= 8
        scores["dolly_varden"] -= 6

    return {key: max(0, min(100, round(value))) for key, value in scores.items()}


def _score_confidence(score_input: ScoreInput, reasons: list[str]) -> tuple[float, str]:
    confidence = score_input.confidence
    if score_input.source_freshness_hours:
        confidence = max(confidence, 0.72)

    stale_sources = [
        source
        for source, age_hours in score_input.source_freshness_hours.items()
        if age_hours > FRESHNESS_LIMIT_HOURS.get(source, 24)
    ]
    if stale_sources:
        confidence -= 0.08 * len(stale_sources)
        reasons.append(f"Stale source data: {', '.join(sorted(stale_sources))}.")

    if score_input.missing_sources:
        confidence -= 0.10 * len(score_input.missing_sources)
        reasons.append(f"Missing required source data: {', '.join(score_input.missing_sources)}.")

    if score_input.missing_sources:
        status = "missing"
    elif stale_sources:
        status = "stale"
    elif score_input.source_freshness_hours:
        status = "fresh"
    else:
        status = "missing"

    return max(0.05, min(1.0, round(confidence, 2))), status


def _positive_reasons(reasons: list[str]) -> list[str]:
    keywords = ("comfort", "normal", "minimal", "stable", "deterministic")
    return [reason for reason in reasons if any(keyword in reason.lower() for keyword in keywords)]


def _limiting_reasons(reasons: list[str]) -> list[str]:
    keywords = (
        "warm",
        "stress",
        "cold",
        "high flow",
        "danger",
        "rain",
        "wind",
        "flood",
        "stale",
        "missing",
        "restriction",
        "closure",
    )
    limiting = [
        reason for reason in reasons if any(keyword in reason.lower() for keyword in keywords)
    ]
    return limiting or ["No major limiting factor identified from current deterministic inputs."]


def _confidence_explanation(score_input: ScoreInput, confidence: float) -> str:
    pieces: list[str] = [f"Confidence is {confidence:.2f}."]
    if score_input.missing_sources:
        missing_sources = ", ".join(score_input.missing_sources)
        pieces.append(f"Missing sources reduce confidence: {missing_sources}.")
    stale_sources = [
        source
        for source, age_hours in score_input.source_freshness_hours.items()
        if age_hours > FRESHNESS_LIMIT_HOURS.get(source, 24)
    ]
    if stale_sources:
        pieces.append(f"Stale sources reduce confidence: {', '.join(sorted(stale_sources))}.")
    if len(pieces) == 1:
        pieces.append("Required source freshness did not trigger a confidence penalty.")
    return " ".join(pieces)


def _score_delta_reason(score: int) -> str:
    if score >= 85:
        return "Strong water, weather, fish, or access signals lifted the score."
    if score >= 70:
        return "Mostly favorable deterministic signals support a good score."
    if score >= 40:
        return "Mixed or incomplete signals keep the score in a fair range."
    return "Limiting, stale, missing, or unsafe signals pushed the score down."


def _recommended_user_action(status: str, score_input: ScoreInput) -> str:
    if score_input.flood_alert_active:
        return "Prioritize safety and check NWS river/weather alerts before going."
    if status in {"excellent", "good"}:
        return "Conditions look fishable, but verify current regulations before heading out."
    if status == "fair":
        return "Check the limiting factors and choose conservative access or timing."
    return "Treat conditions as uncertain and verify official sources before making plans."


def _legal_uncertainty_explanation() -> str:
    return (
        "An active ADF&G order could not be confidently classified; this is not a legal "
        "permission determination."
    )


def _legal_uncertainty_action() -> str:
    return "Verify the official ADF&G order before making fishing plans."
