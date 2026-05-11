"""USGS instantaneous-values source adapter."""

from __future__ import annotations

import json

import httpx
from pydantic import BaseModel

from kenai_engine.config import Settings
from kenai_engine.models import UsgsFlowStatistic, UsgsObservation
from kenai_engine.utils.http import build_http_client
from kenai_engine.utils.time import utc_now

USGS_IV_URL = "https://waterservices.usgs.gov/nwis/iv/"
USGS_LATEST_CONTINUOUS_URL = (
    "https://api.waterdata.usgs.gov/ogcapi/v0/collections/latest-continuous/items"
)
USGS_STATISTICS_URL = "https://waterservices.usgs.gov/nwis/stat/"
CORE_USGS_PARAMETER_CODES = ("00060", "00065", "00010", "63680")
EXPANDED_USGS_PARAMETER_CODES = (
    "00060",
    "00065",
    "00010",
    "63680",
    "00095",
    "00300",
    "00400",
)
USGS_PARAMETER_CODES = EXPANDED_USGS_PARAMETER_CODES
USGS_PARAMETER_MAPPING = {
    "00060": {"name": "discharge", "unit": "ft3/s", "priority": "must_have"},
    "00065": {"name": "gage_height", "unit": "ft", "priority": "must_have"},
    "00010": {"name": "water_temperature", "unit": "degC", "priority": "must_have"},
    "63680": {"name": "turbidity", "unit": "FNU", "priority": "high_if_available"},
    "00095": {"name": "specific_conductance", "unit": "uS/cm", "priority": "medium"},
    "00300": {"name": "dissolved_oxygen", "unit": "mg/L", "priority": "medium_if_available"},
    "00400": {"name": "ph", "unit": "standard units", "priority": "low_medium"},
}


class RawSnapshot(BaseModel):
    """Raw source payload captured by an adapter."""

    source: str
    fetched_at: str
    payload: str


class UsgsAdapter:
    """USGS instantaneous-values adapter."""

    source_name = "usgs"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = client

    def fetch(self) -> RawSnapshot:
        client = self._client or build_http_client(self._settings)
        should_close = self._client is None
        try:
            response = client.get(
                USGS_IV_URL,
                params={
                    "format": "json",
                    "sites": ",".join(
                        normalize_monitoring_location_id(site_id)[1]
                        for site_id in self._settings.usgs_site_ids
                    ),
                    "parameterCd": ",".join(USGS_PARAMETER_CODES),
                    "siteStatus": "all",
                    "period": "PT24H",
                },
            )
            response.raise_for_status()
            payload = response.text
        finally:
            if should_close:
                client.close()

        return RawSnapshot(
            source=self.source_name,
            fetched_at=utc_now().isoformat(),
            payload=payload,
        )


class UsgsModernAdapter:
    """USGS OGC latest-continuous adapter."""

    source_name = "usgs"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = client

    def fetch(self) -> RawSnapshot:
        client = self._client or build_http_client(self._settings)
        should_close = self._client is None
        try:
            response = client.get(
                USGS_LATEST_CONTINUOUS_URL,
                params={
                    "f": "json",
                    "monitoring_location_id": ",".join(
                        normalize_monitoring_location_id(site_id)[0]
                        for site_id in self._settings.usgs_site_ids
                    ),
                    "parameter_code": ",".join(USGS_PARAMETER_CODES),
                },
            )
            response.raise_for_status()
            payload = response.text
        finally:
            if should_close:
                client.close()

        return RawSnapshot(
            source=self.source_name,
            fetched_at=utc_now().isoformat(),
            payload=payload,
        )


class UsgsStatisticsAdapter:
    """USGS daily statistics adapter for historical discharge percentiles."""

    source_name = "usgs_statistics"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = client

    def fetch(self) -> RawSnapshot:
        client = self._client or build_http_client(self._settings)
        should_close = self._client is None
        try:
            response = client.get(
                USGS_STATISTICS_URL,
                params={
                    "format": "rdb",
                    "sites": ",".join(self._settings.usgs_site_ids),
                    "parameterCd": "00060",
                    "statReportType": "daily",
                    "statType": "P25,P50,P75,P90,P95",
                },
            )
            response.raise_for_status()
            payload = response.text
        finally:
            if should_close:
                client.close()

        return RawSnapshot(
            source=self.source_name,
            fetched_at=utc_now().isoformat(),
            payload=payload,
        )


def parse_usgs_payload(payload: str) -> list[UsgsObservation]:
    """Parse USGS latest-continuous GeoJSON or WaterML JSON into observations."""

    document = json.loads(payload)
    if isinstance(document, dict) and isinstance(document.get("features"), list):
        return _parse_usgs_latest_continuous_payload(document)

    observations: list[UsgsObservation] = []

    for series in document.get("value", {}).get("timeSeries", []):
        source_info = series.get("sourceInfo", {})
        variable = series.get("variable", {})
        raw_site_id = _first_value(source_info.get("siteCode"))
        monitoring_location_id, site_id = normalize_monitoring_location_id(raw_site_id)
        parameter_code = _first_value(variable.get("variableCode"))
        site_name = source_info.get("siteName", "")
        parameter_name = USGS_PARAMETER_MAPPING.get(parameter_code, {}).get("name") or variable.get(
            "variableName", ""
        )
        unit = variable.get("unit", {}).get("unitCode", "")

        for values_group in series.get("values", []):
            for reading in values_group.get("value", []):
                raw_value = reading.get("value")
                observed_at = reading.get("dateTime")
                if site_id and parameter_code and raw_value is not None and observed_at:
                    observations.append(
                        UsgsObservation(
                            site_id=site_id,
                            monitoring_location_id=monitoring_location_id,
                            site_name=site_name,
                            parameter_code=parameter_code,
                            parameter_name=parameter_name,
                            value=float(raw_value),
                            unit=unit,
                            observed_at=observed_at,
                            qualifiers=reading.get("qualifiers", []),
                        )
                    )

    return observations


def _parse_usgs_latest_continuous_payload(document: dict[str, object]) -> list[UsgsObservation]:
    observations: list[UsgsObservation] = []
    features = document.get("features")
    if not isinstance(features, list):
        return observations

    for feature in features:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            continue

        raw_site_id = _string_property(
            properties,
            "monitoring_location_id",
            "monitoringLocationId",
            "monitoringLocationIdentifier",
        )
        monitoring_location_id, site_id = normalize_monitoring_location_id(raw_site_id)
        parameter_code = _string_property(properties, "parameter_code", "parameterCode")
        raw_value = properties.get("value")
        observed_at = _string_property(
            properties,
            "time",
            "phenomenon_time",
            "phenomenonTime",
            "dateTime",
        )
        if not site_id or not parameter_code or raw_value is None or not observed_at:
            continue

        parameter_name = USGS_PARAMETER_MAPPING.get(parameter_code, {}).get(
            "name"
        ) or _string_property(properties, "parameter_name", "parameterName")
        observations.append(
            UsgsObservation(
                site_id=site_id,
                monitoring_location_id=monitoring_location_id,
                site_name=_string_property(
                    properties,
                    "monitoring_location_name",
                    "monitoringLocationName",
                    "name",
                ),
                parameter_code=parameter_code,
                parameter_name=parameter_name,
                value=float(raw_value),
                unit=_string_property(properties, "unit_of_measure", "unitOfMeasure", "unit"),
                observed_at=observed_at,
                qualifiers=_qualifiers_from_properties(properties),
            )
        )

    return observations


def normalize_monitoring_location_id(value: str) -> tuple[str, str]:
    """Return canonical OGC monitoring-location ID and NWIS numeric site ID."""

    normalized = value.strip()
    if normalized.upper().startswith("USGS:"):
        normalized = normalized.split(":", 1)[1]
    if normalized.upper().startswith("USGS-"):
        nwis_site_id = normalized.split("-", 1)[1]
    else:
        nwis_site_id = normalized
    return f"USGS-{nwis_site_id}", nwis_site_id


def classify_usgs_trend(
    observations: list[UsgsObservation],
    *,
    parameter_code: str = "00065",
    stable_threshold: float = 0.25,
    noisy_latest_threshold: float = 0.5,
) -> dict[str, object]:
    """Classify trend from a recent USGS observation window.

    Uses the median of the first and last three readings where available so one
    noisy last transmission does not dominate the trend.
    """

    parameter_observations = [
        observation for observation in observations if observation.parameter_code == parameter_code
    ]
    matching = sorted(parameter_observations, key=lambda observation: observation.observed_at)
    if len(matching) < 2:
        return {"classification": "unknown", "window_minutes": 0, "sample_count": len(matching)}

    first_values = [observation.value for observation in matching[:3]]
    last_values = [observation.value for observation in matching[-3:]]
    first = _median(first_values)
    last = _median(last_values)
    raw_latest_delta = matching[-1].value - matching[-2].value if len(matching) >= 2 else 0.0
    delta = last - first
    likely_noisy_latest = (
        abs(raw_latest_delta) > noisy_latest_threshold and abs(delta) <= stable_threshold * 2
    )
    if likely_noisy_latest or abs(delta) <= stable_threshold:
        classification = "stable"
    elif delta > 0:
        classification = "rising"
    else:
        classification = "falling"

    window_minutes = round(
        (matching[-1].observed_at - matching[0].observed_at).total_seconds() / 60
    )
    return {
        "classification": classification,
        "delta": round(delta, 2),
        "window_minutes": window_minutes,
        "sample_count": len(matching),
    }


def parse_usgs_statistics_payload(payload: str) -> list[UsgsFlowStatistic]:
    """Parse USGS statistics JSON into day-of-year percentile records."""

    try:
        document = json.loads(payload)
    except json.JSONDecodeError:
        return _parse_usgs_statistics_rdb(payload)
    statistics: list[UsgsFlowStatistic] = []

    for series in document.get("value", {}).get("timeSeries", []):
        source_info = series.get("sourceInfo", {})
        variable = series.get("variable", {})
        site_id = _first_value(source_info.get("siteCode"))
        parameter_code = _first_value(variable.get("variableCode")) or "00060"
        unit = variable.get("unit", {}).get("unitCode", "")

        for values_group in series.get("values", []):
            for row in values_group.get("value", []):
                if not isinstance(row, dict):
                    continue
                month = _int_value(row.get("month_nu") or row.get("month"))
                day = _int_value(row.get("day_nu") or row.get("day"))
                if site_id and month is not None and day is not None:
                    statistics.append(
                        UsgsFlowStatistic(
                            site_id=site_id,
                            month=month,
                            day=day,
                            parameter_code=parameter_code,
                            unit=unit,
                            p25=_float_value(row.get("p25_va") or row.get("p25")),
                            p50=_float_value(row.get("p50_va") or row.get("p50")),
                            p75=_float_value(row.get("p75_va") or row.get("p75")),
                            p90=_float_value(row.get("p90_va") or row.get("p90")),
                            p95=_float_value(row.get("p95_va") or row.get("p95")),
                        )
                    )

    return statistics


def _parse_usgs_statistics_rdb(payload: str) -> list[UsgsFlowStatistic]:
    rows = [
        line
        for line in payload.splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if len(rows) < 3:
        return []
    headers = rows[0].split("\t")
    statistics: list[UsgsFlowStatistic] = []
    for row in rows[2:]:
        values = row.split("\t")
        record = {
            header: values[index]
            for index, header in enumerate(headers)
            if index < len(values)
        }
        site_id = record.get("site_no", "")
        month = _int_value(record.get("month_nu"))
        day = _int_value(record.get("day_nu"))
        if not site_id or month is None or day is None:
            continue
        statistics.append(
            UsgsFlowStatistic(
                site_id=site_id,
                month=month,
                day=day,
                parameter_code=record.get("parameter_cd", "00060"),
                unit="ft3/s",
                p25=_float_value(record.get("p25_va")),
                p50=_float_value(record.get("p50_va")),
                p75=_float_value(record.get("p75_va")),
                p90=_float_value(record.get("p90_va")),
                p95=_float_value(record.get("p95_va")),
            )
        )
    return statistics


def calculate_flow_percentile(flow_cfs: float, statistic: UsgsFlowStatistic) -> float | None:
    """Estimate flow percentile by interpolating USGS percentile classes."""

    points = [
        (25.0, statistic.p25),
        (50.0, statistic.p50),
        (75.0, statistic.p75),
        (90.0, statistic.p90),
        (95.0, statistic.p95),
    ]
    numeric_points = [(percentile, value) for percentile, value in points if value is not None]
    if len(numeric_points) < 2:
        return None
    if flow_cfs <= numeric_points[0][1]:
        return numeric_points[0][0]
    for (low_percentile, low_value), (high_percentile, high_value) in zip(
        numeric_points,
        numeric_points[1:],
        strict=False,
    ):
        if low_value <= flow_cfs <= high_value:
            if high_value == low_value:
                return high_percentile
            fraction = (flow_cfs - low_value) / (high_value - low_value)
            return round(low_percentile + fraction * (high_percentile - low_percentile), 1)
    return numeric_points[-1][0]


def _first_value(items: object) -> str:
    if not isinstance(items, list) or not items:
        return ""
    first = items[0]
    if not isinstance(first, dict):
        return ""
    value = first.get("value")
    return value if isinstance(value, str) else ""


def _string_property(properties: dict[object, object], *keys: str) -> str:
    for key in keys:
        value = properties.get(key)
        if isinstance(value, str):
            return value
    return ""


def _qualifiers_from_properties(properties: dict[object, object]) -> list[str]:
    qualifiers = properties.get("qualifiers")
    if isinstance(qualifiers, list):
        return [qualifier for qualifier in qualifiers if isinstance(qualifier, str)]
    if isinstance(qualifiers, str):
        return [qualifiers]
    approval_status = properties.get("approval_status") or properties.get("approvalStatus")
    if isinstance(approval_status, str) and approval_status:
        return [approval_status]
    return []


def _int_value(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _float_value(value: object) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2
