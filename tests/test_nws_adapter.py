import json

import httpx

from kenai_engine.config import Settings
from kenai_engine.sources.nws import NwsAdapter, parse_nws_alerts


def _settings(tmp_path) -> Settings:
    return Settings(
        user_agent="test-agent",
        db_path=tmp_path / "db.sqlite3",
        output_dir=tmp_path / "reports",
        raw_dir=tmp_path / "raw",
        usgs_site_ids=["15266300"],
        nws_locations=["Kenai,AK"],
        fetch_timeout_seconds=1,
    )


def test_nws_adapter_fetches_alerts_and_forecast_for_default_kenai_point(tmp_path) -> None:
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        if request.url.path == "/alerts/active":
            return httpx.Response(200, json={"type": "FeatureCollection", "features": []})
        if request.url.path == "/points/60.5544,-151.2583":
            return httpx.Response(
                200,
                json={
                    "properties": {
                        "forecast": "https://api.weather.gov/gridpoints/AFC/145,136/forecast"
                    }
                },
            )
        if request.url.path == "/gridpoints/AFC/145,136/forecast":
            return httpx.Response(200, json={"properties": {"periods": []}})
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    snapshot = NwsAdapter(_settings(tmp_path), client=client).fetch()

    assert snapshot.source == "nws"
    payload = json.loads(snapshot.payload)
    assert payload == {
        "locations": [
            {
                "location": "Kenai,AK",
                "point": "60.5544,-151.2583",
                "alerts": {"type": "FeatureCollection", "features": []},
                "forecast": {"properties": {"periods": []}},
            }
        ]
    }
    paths = [request.url.path for request in seen_requests]
    assert paths == [
        "/alerts/active",
        "/points/60.5544,-151.2583",
        "/gridpoints/AFC/145,136/forecast",
    ]
    alert_params = dict(seen_requests[0].url.params.multi_items())
    assert alert_params["point"] == "60.5544,-151.2583"


def test_parse_nws_alerts_extracts_simple_alert_records() -> None:
    payload = json.dumps(
        {
            "locations": [
                {
                    "location": "Kenai,AK",
                    "alerts": {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "properties": {
                                    "event": "Flood Warning",
                                    "severity": "Severe",
                                    "headline": "Flood Warning issued for Kenai River",
                                    "description": "Minor flooding is occurring.",
                                    "senderName": "NWS Anchorage",
                                }
                            },
                            {
                                "properties": {
                                    "event": "Hydrologic Outlook",
                                    "severity": "Moderate",
                                    "description": "Rises are possible next week.",
                                    "senderName": "NWS Alaska Pacific River Forecast Center",
                                }
                            },
                            {
                                "properties": {
                                    "event": "Special Weather Statement",
                                    "severity": "Minor",
                                }
                            },
                        ],
                    },
                }
            ]
        }
    )

    alerts = parse_nws_alerts(payload)

    assert [alert.model_dump() for alert in alerts] == [
        {
            "title": "Flood Warning",
            "severity": "warning",
            "summary": "Flood Warning issued for Kenai River",
            "source": "NWS Anchorage",
        },
        {
            "title": "Hydrologic Outlook",
            "severity": "watch",
            "summary": "Rises are possible next week.",
            "source": "NWS Alaska Pacific River Forecast Center",
        },
        {
            "title": "Special Weather Statement",
            "severity": "info",
            "summary": "",
            "source": "nws",
        },
    ]
