import json
from datetime import UTC, datetime

import httpx

from kenai_engine.config import Settings
from kenai_engine.sources.noaa_tides import (
    NoaaTidesAdapter,
    determine_tide_stage,
    parse_tide_predictions,
)


def _settings(tmp_path) -> Settings:
    return Settings(
        user_agent="test-agent",
        db_path=tmp_path / "db.sqlite3",
        output_dir=tmp_path / "reports",
        raw_dir=tmp_path / "raw",
        usgs_site_ids=["15266300"],
        nws_locations=["Kenai,AK"],
        fetch_timeout_seconds=1,
        noaa_tide_station_id="9455742",
    )


def test_noaa_tides_adapter_fetches_predictions_for_configured_station(tmp_path) -> None:
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(200, json={"predictions": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))

    snapshot = NoaaTidesAdapter(_settings(tmp_path), client=client).fetch()

    assert snapshot.source == "noaa_tides"
    assert json.loads(snapshot.payload) == {"predictions": []}
    params = dict(seen_requests[0].url.params.multi_items())
    assert params["station"] == "9455742"
    assert params["product"] == "predictions"
    assert params["interval"] == "hilo"
    assert params["units"] == "english"
    assert "begin_date" in params
    assert "end_date" in params
    assert "range" not in params


def test_parse_tide_predictions_extracts_high_low_predictions() -> None:
    payload = json.dumps(
        {
            "predictions": [
                {"t": "2026-07-22 06:00", "v": "2.1", "type": "L"},
                {"t": "2026-07-22 12:15", "v": "20.4", "type": "H"},
            ]
        }
    )

    predictions = parse_tide_predictions(payload, source_url="https://api.tides.example")

    assert [prediction.model_dump(mode="json") for prediction in predictions] == [
        {
            "station_id": "9455742",
            "predicted_at": "2026-07-22T06:00:00Z",
            "height_ft": 2.1,
            "tide_type": "L",
            "source_url": "https://api.tides.example",
        },
        {
            "station_id": "9455742",
            "predicted_at": "2026-07-22T12:15:00Z",
            "height_ft": 20.4,
            "tide_type": "H",
            "source_url": "https://api.tides.example",
        },
    ]


def test_determine_tide_stage_between_low_and_high_is_incoming() -> None:
    predictions = parse_tide_predictions(
        json.dumps(
            {
                "predictions": [
                    {"t": "2026-07-22 06:00", "v": "2.1", "type": "L"},
                    {"t": "2026-07-22 12:15", "v": "20.4", "type": "H"},
                ]
            }
        )
    )

    stage = determine_tide_stage(predictions, datetime(2026, 7, 22, 9, 0, tzinfo=UTC))

    assert stage == "incoming"
