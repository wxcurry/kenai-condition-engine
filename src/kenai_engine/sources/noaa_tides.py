"""NOAA CO-OPS tide prediction adapter."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx

from kenai_engine.config import Settings
from kenai_engine.models import TidePrediction
from kenai_engine.sources.usgs import RawSnapshot
from kenai_engine.utils.http import build_http_client
from kenai_engine.utils.time import utc_now

NOAA_TIDES_API_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"


class NoaaTidesAdapter:
    """NOAA tide prediction adapter for the lower Kenai."""

    source_name = "noaa_tides"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = client

    def fetch(self) -> RawSnapshot:
        client = self._client or build_http_client(self._settings)
        should_close = self._client is None
        today = utc_now().date()
        tomorrow = today + timedelta(days=1)
        try:
            response = client.get(
                NOAA_TIDES_API_URL,
                params={
                    "product": "predictions",
                    "application": "kenai-condition-engine",
                    "station": self._settings.noaa_tide_station_id,
                    "datum": "MLLW",
                    "time_zone": "gmt",
                    "units": "english",
                    "interval": "hilo",
                    "format": "json",
                    "begin_date": today.strftime("%Y%m%d"),
                    "end_date": tomorrow.strftime("%Y%m%d"),
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


def parse_tide_predictions(
    payload: str,
    *,
    station_id: str = "9455742",
    source_url: str | None = None,
) -> list[TidePrediction]:
    """Parse NOAA tide-prediction JSON."""

    document = json.loads(payload)
    predictions = document.get("predictions") if isinstance(document, dict) else None
    if not isinstance(predictions, list):
        return []

    parsed: list[TidePrediction] = []
    for prediction in predictions:
        if not isinstance(prediction, dict):
            continue
        predicted_at = _parse_prediction_time(prediction.get("t"))
        tide_type = prediction.get("type")
        height = prediction.get("v")
        if predicted_at is None or tide_type not in {"H", "L"}:
            continue
        try:
            height_ft = float(str(height))
        except (TypeError, ValueError):
            continue
        parsed.append(
            TidePrediction(
                station_id=station_id,
                predicted_at=predicted_at,
                height_ft=height_ft,
                tide_type=tide_type,
                source_url=source_url,
            )
        )
    return parsed


def determine_tide_stage(
    predictions: list[TidePrediction],
    current_time: datetime,
) -> str:
    """Return a simple lower-river tide stage from surrounding high/low predictions."""

    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=UTC)
    sorted_predictions = sorted(predictions, key=lambda prediction: prediction.predicted_at)
    previous_prediction: TidePrediction | None = None
    next_prediction: TidePrediction | None = None
    for prediction in sorted_predictions:
        if prediction.predicted_at <= current_time:
            previous_prediction = prediction
        elif prediction.predicted_at > current_time:
            next_prediction = prediction
            break

    if previous_prediction is None or next_prediction is None:
        return "unknown"
    minutes_from_previous = (
        abs((current_time - previous_prediction.predicted_at).total_seconds()) / 60
    )
    minutes_to_next = abs((next_prediction.predicted_at - current_time).total_seconds()) / 60
    if previous_prediction.tide_type == "H" and minutes_from_previous <= 60:
        return "high"
    if previous_prediction.tide_type == "L" and minutes_from_previous <= 60:
        return "low"
    if next_prediction.tide_type == "H" and minutes_to_next <= 60:
        return "high"
    if next_prediction.tide_type == "L" and minutes_to_next <= 60:
        return "low"
    if previous_prediction.tide_type == "L" and next_prediction.tide_type == "H":
        return "incoming"
    if previous_prediction.tide_type == "H" and next_prediction.tide_type == "L":
        return "outgoing"
    return "unknown"


def _parse_prediction_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
    except ValueError:
        return None
