"""National Weather Service source adapter."""

from __future__ import annotations

import json

import httpx

from kenai_engine.config import Settings
from kenai_engine.models import Alert
from kenai_engine.sources.usgs import RawSnapshot
from kenai_engine.utils.http import build_http_client
from kenai_engine.utils.time import utc_now

NWS_API_BASE_URL = "https://api.weather.gov"
NWS_ALERTS_URL = f"{NWS_API_BASE_URL}/alerts/active"
NWS_POINTS_URL = f"{NWS_API_BASE_URL}/points"
DEFAULT_KENAI_POINT = "60.5544,-151.2583"


class NwsAdapter:
    """NWS alerts and forecast adapter."""

    source_name = "nws"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = client

    def fetch(self) -> RawSnapshot:
        client = self._client or build_http_client(self._settings)
        should_close = self._client is None
        try:
            locations = [
                self._fetch_location(client, location) for location in self._settings.nws_locations
            ]
        finally:
            if should_close:
                client.close()

        return RawSnapshot(
            source=self.source_name,
            fetched_at=utc_now().isoformat(),
            payload=json.dumps({"locations": locations}),
        )

    def _fetch_location(self, client: httpx.Client, location: str) -> dict[str, object]:
        point = _point_for_location(location)

        alerts_response = client.get(NWS_ALERTS_URL, params={"point": point})
        alerts_response.raise_for_status()
        alerts = alerts_response.json()

        points_response = client.get(f"{NWS_POINTS_URL}/{point}")
        points_response.raise_for_status()
        forecast_url = points_response.json().get("properties", {}).get("forecast")

        forecast: dict[str, object] = {}
        if isinstance(forecast_url, str) and forecast_url:
            forecast_response = client.get(forecast_url)
            forecast_response.raise_for_status()
            forecast = forecast_response.json()

        return {
            "location": location,
            "point": point,
            "alerts": alerts,
            "forecast": forecast,
        }


def parse_nws_alerts(payload: str) -> list[Alert]:
    """Parse NWS GeoJSON alert features into normalized alerts."""

    document = json.loads(payload)
    alerts: list[Alert] = []

    for feature in _iter_alert_features(document):
        properties = feature.get("properties", {})
        if not isinstance(properties, dict):
            continue

        title = _string_value(properties.get("event")) or _string_value(properties.get("title"))
        if not title:
            continue

        summary = _string_value(properties.get("headline")) or _string_value(
            properties.get("description")
        )
        source = _string_value(properties.get("senderName")) or _string_value(
            properties.get("source")
        )
        alerts.append(
            Alert(
                title=title,
                severity=_map_severity(properties.get("severity")),
                summary=summary,
                source=source or "nws",
            )
        )

    return alerts


def _iter_alert_features(document: object) -> list[dict[str, object]]:
    if not isinstance(document, dict):
        return []

    direct_features = document.get("features")
    if isinstance(direct_features, list):
        return [feature for feature in direct_features if isinstance(feature, dict)]

    features: list[dict[str, object]] = []
    locations = document.get("locations")
    if not isinstance(locations, list):
        return features

    for location in locations:
        if not isinstance(location, dict):
            continue
        alerts = location.get("alerts")
        if not isinstance(alerts, dict):
            continue
        location_features = alerts.get("features")
        if isinstance(location_features, list):
            features.extend(feature for feature in location_features if isinstance(feature, dict))

    return features


def _map_severity(value: object) -> str:
    severity = _string_value(value).lower()
    if severity in {"extreme", "severe"}:
        return "warning"
    if severity == "moderate":
        return "watch"
    return "info"


def _point_for_location(location: str) -> str:
    if location.strip().lower() == "kenai,ak":
        return DEFAULT_KENAI_POINT
    return DEFAULT_KENAI_POINT


def _string_value(value: object) -> str:
    return value if isinstance(value, str) else ""
