"""National Weather Service source adapter."""

from __future__ import annotations

import json
from datetime import datetime

import httpx

from kenai_engine.config import Settings
from kenai_engine.models import Alert, WeatherObservation
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
        point_properties = points_response.json().get("properties", {})
        forecast_url = point_properties.get("forecast")
        hourly_forecast_url = point_properties.get("forecastHourly")
        forecast_grid_url = point_properties.get("forecastGridData")
        observation_stations_url = point_properties.get("observationStations")

        latest_observations = _fetch_latest_observations(client, observation_stations_url)

        forecast: dict[str, object] = {}
        if isinstance(forecast_url, str) and forecast_url:
            forecast_response = client.get(forecast_url)
            forecast_response.raise_for_status()
            forecast = forecast_response.json()
        hourly_forecast: dict[str, object] = {}
        if isinstance(hourly_forecast_url, str) and hourly_forecast_url:
            hourly_response = client.get(hourly_forecast_url)
            hourly_response.raise_for_status()
            hourly_forecast = hourly_response.json()
        forecast_grid: dict[str, object] = {}
        if isinstance(forecast_grid_url, str) and forecast_grid_url:
            grid_response = client.get(forecast_grid_url)
            grid_response.raise_for_status()
            forecast_grid = grid_response.json()

        return {
            "location": location,
            "point": point,
            "alerts": alerts,
            "forecast": forecast,
            "hourly_forecast": hourly_forecast,
            "forecast_grid": forecast_grid,
            "latest_observations": latest_observations,
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


def parse_nws_weather(payload: str) -> list[WeatherObservation]:
    """Parse NWS grid forecast data into scoring signals."""

    document = json.loads(payload)
    if not isinstance(document, dict):
        return []
    locations = document.get("locations")
    if not isinstance(locations, list):
        return []

    observations: list[WeatherObservation] = []
    for location in locations:
        if not isinstance(location, dict):
            continue
        observations.extend(_parse_latest_station_observations(location))

        location_name = _string_value(location.get("location"))
        forecast_grid = location.get("forecast_grid")
        if not isinstance(forecast_grid, dict):
            continue
        properties = forecast_grid.get("properties")
        if not isinstance(properties, dict):
            continue

        rain_inches = _precip_inches(properties.get("quantitativePrecipitation"))
        wind_mph = _wind_mph(properties.get("windSpeed"))
        hourly = _first_hourly_period(location.get("hourly_forecast"))
        temperature_f = _temperature_f(hourly)
        wind_direction = _string_value(hourly.get("windDirection")) if hourly else None
        short_forecast = _string_value(hourly.get("shortForecast")) if hourly else None
        detailed_forecast = _string_value(hourly.get("detailedForecast")) if hourly else None
        precipitation_probability = _precip_probability(hourly)
        if (
            rain_inches is None
            and wind_mph is None
            and temperature_f is None
            and not short_forecast
        ):
            continue
        observations.append(
            WeatherObservation(
                location=location_name or "Kenai,AK",
                observed_at=utc_now(),
                recent_rain_inches_24h=rain_inches,
                wind_mph=wind_mph,
                temperature_f=temperature_f,
                wind_direction=wind_direction,
                short_forecast=short_forecast,
                precipitation_probability=precipitation_probability,
                detailed_forecast=detailed_forecast,
                source="nws",
            )
        )
    return observations


def _fetch_latest_observations(
    client: httpx.Client,
    observation_stations_url: object,
    *,
    station_limit: int = 3,
) -> list[dict[str, object]]:
    if not isinstance(observation_stations_url, str) or not observation_stations_url:
        return []

    stations_response = client.get(observation_stations_url)
    stations_response.raise_for_status()
    stations_document = stations_response.json()
    features = stations_document.get("features") if isinstance(stations_document, dict) else None
    if not isinstance(features, list):
        return []

    latest_observations: list[dict[str, object]] = []
    for feature in features[:station_limit]:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            continue
        station_id = _string_value(properties.get("stationIdentifier"))
        if not station_id:
            continue
        observation_response = client.get(
            f"{NWS_API_BASE_URL}/stations/{station_id}/observations/latest"
        )
        observation_response.raise_for_status()
        latest_observations.append(
            {
                "station_id": station_id,
                "station_name": _string_value(properties.get("name")),
                "observation": observation_response.json(),
            }
        )
    return latest_observations


def _parse_latest_station_observations(location: dict[str, object]) -> list[WeatherObservation]:
    latest_observations = location.get("latest_observations")
    if not isinstance(latest_observations, list):
        return []

    weather: list[WeatherObservation] = []
    for station in latest_observations:
        if not isinstance(station, dict):
            continue
        observation = station.get("observation")
        if not isinstance(observation, dict):
            continue
        properties = observation.get("properties")
        if not isinstance(properties, dict):
            continue

        station_id = _string_value(station.get("station_id"))
        observed_at = _datetime_value(properties.get("timestamp"))
        temperature_f = _celsius_property_to_f(properties.get("temperature"))
        wind_mph = _kmh_property_to_mph(properties.get("windSpeed"))
        rain_inches = _mm_property_to_inches(properties.get("precipitationLastHour"))
        short_forecast = _string_value(properties.get("textDescription"))
        if (
            observed_at is None
            or (
                temperature_f is None
                and wind_mph is None
                and rain_inches is None
                and not short_forecast
            )
        ):
            continue

        weather.append(
            WeatherObservation(
                location=_string_value(station.get("station_name"))
                or station_id
                or _string_value(location.get("location"))
                or "Kenai,AK",
                observed_at=observed_at,
                recent_rain_inches_24h=rain_inches,
                wind_mph=wind_mph,
                temperature_f=temperature_f,
                wind_direction=_property_value_string(properties.get("windDirection")),
                short_forecast=short_forecast,
                source=f"nws:{station_id}" if station_id else "nws",
            )
        )
    return weather


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


def _precip_inches(layer: object) -> float | None:
    if not isinstance(layer, dict):
        return None
    values = layer.get("values")
    if not isinstance(values, list):
        return None
    total_mm = 0.0
    found = False
    for row in values[:8]:
        if not isinstance(row, dict):
            continue
        value = row.get("value")
        if isinstance(value, int | float):
            total_mm += float(value)
            found = True
    if not found:
        return None
    return round(total_mm / 25.4, 2)


def _wind_mph(layer: object) -> float | None:
    if not isinstance(layer, dict):
        return None
    values = layer.get("values")
    if not isinstance(values, list):
        return None
    for row in values:
        if not isinstance(row, dict):
            continue
        value = row.get("value")
        if isinstance(value, int | float):
            return round(float(value) * 0.621371, 1)
    return None


def _first_hourly_period(hourly_forecast: object) -> dict[str, object] | None:
    if not isinstance(hourly_forecast, dict):
        return None
    properties = hourly_forecast.get("properties")
    if not isinstance(properties, dict):
        return None
    periods = properties.get("periods")
    if not isinstance(periods, list) or not periods:
        return None
    first = periods[0]
    return first if isinstance(first, dict) else None


def _temperature_f(period: dict[str, object] | None) -> float | None:
    if period is None:
        return None
    value = period.get("temperature")
    unit = _string_value(period.get("temperatureUnit")).upper()
    if not isinstance(value, int | float):
        return None
    if unit == "F":
        return float(value)
    if unit == "C":
        return round(float(value) * 9 / 5 + 32, 1)
    return None


def _precip_probability(period: dict[str, object] | None) -> int | None:
    if period is None:
        return None
    probability = period.get("probabilityOfPrecipitation")
    if not isinstance(probability, dict):
        return None
    value = probability.get("value")
    if isinstance(value, int | float):
        return round(value)
    return None


def _datetime_value(value: object) -> datetime | None:
    raw_value = _string_value(value)
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _celsius_property_to_f(layer: object) -> float | None:
    value = _property_numeric_value(layer)
    if value is None:
        return None
    return round(value * 9 / 5 + 32, 1)


def _kmh_property_to_mph(layer: object) -> float | None:
    value = _property_numeric_value(layer)
    if value is None:
        return None
    return round(value * 0.621371, 1)


def _mm_property_to_inches(layer: object) -> float | None:
    value = _property_numeric_value(layer)
    if value is None:
        return None
    return round(value / 25.4, 2)


def _property_numeric_value(layer: object) -> float | None:
    if not isinstance(layer, dict):
        return None
    value = layer.get("value")
    if isinstance(value, int | float):
        return float(value)
    return None


def _property_value_string(layer: object) -> str | None:
    value = _property_numeric_value(layer)
    if value is None:
        return None
    if value.is_integer():
        return str(int(value))
    return str(value)


def _point_for_location(location: str) -> str:
    if location.strip().lower() == "kenai,ak":
        return DEFAULT_KENAI_POINT
    return DEFAULT_KENAI_POINT


def _string_value(value: object) -> str:
    return value if isinstance(value, str) else ""
