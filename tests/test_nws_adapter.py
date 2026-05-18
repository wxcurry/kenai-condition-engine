import json

import httpx

from kenai_engine.config import Settings
from kenai_engine.sources.nws import NwsAdapter, parse_nws_alerts, parse_nws_weather


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
                        "forecast": "https://api.weather.gov/gridpoints/AFC/145,136/forecast",
                        "forecastHourly": (
                            "https://api.weather.gov/gridpoints/AFC/145,136/forecast/hourly"
                        ),
                        "forecastGridData": (
                            "https://api.weather.gov/gridpoints/AFC/145,136"
                        ),
                        "observationStations": (
                            "https://api.weather.gov/gridpoints/AFC/145,136/stations"
                        ),
                    }
                },
            )
        if request.url.path == "/gridpoints/AFC/145,136/stations":
            return httpx.Response(
                200,
                json={
                    "features": [
                        {
                            "properties": {
                                "stationIdentifier": "PAEN",
                                "name": "Kenai Municipal Airport",
                            }
                        }
                    ]
                },
            )
        if request.url.path == "/stations/PAEN/observations/latest":
            return httpx.Response(
                200,
                json={
                    "properties": {
                        "station": "https://api.weather.gov/stations/PAEN",
                        "timestamp": "2026-05-02T17:30:00+00:00",
                        "temperature": {"unitCode": "wmoUnit:degC", "value": 6.0},
                        "windSpeed": {"unitCode": "wmoUnit:km_h-1", "value": 35.186},
                        "windDirection": {"unitCode": "wmoUnit:degree_(angle)", "value": 200},
                        "precipitationLastHour": {"unitCode": "wmoUnit:mm", "value": 2.54},
                        "textDescription": "Clear and Windy",
                    }
                },
            )
        if request.url.path == "/gridpoints/AFC/145,136/forecast":
            return httpx.Response(200, json={"properties": {"periods": []}})
        if request.url.path == "/gridpoints/AFC/145,136/forecast/hourly":
            return httpx.Response(200, json={"properties": {"periods": []}})
        if request.url.path == "/gridpoints/AFC/145,136":
            return httpx.Response(
                200,
                json={
                    "properties": {
                        "quantitativePrecipitation": {"values": []},
                        "windSpeed": {"values": []},
                    }
                },
            )
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
                "hourly_forecast": {"properties": {"periods": []}},
                "forecast_grid": {
                    "properties": {
                        "quantitativePrecipitation": {"values": []},
                        "windSpeed": {"values": []},
                    }
                },
                "latest_observations": [
                    {
                        "station_id": "PAEN",
                        "station_name": "Kenai Municipal Airport",
                        "observation": {
                            "properties": {
                                "station": "https://api.weather.gov/stations/PAEN",
                                "timestamp": "2026-05-02T17:30:00+00:00",
                                "temperature": {"unitCode": "wmoUnit:degC", "value": 6.0},
                                "windSpeed": {"unitCode": "wmoUnit:km_h-1", "value": 35.186},
                                "windDirection": {
                                    "unitCode": "wmoUnit:degree_(angle)",
                                    "value": 200,
                                },
                                "precipitationLastHour": {
                                    "unitCode": "wmoUnit:mm",
                                    "value": 2.54,
                                },
                                "textDescription": "Clear and Windy",
                            }
                        },
                    }
                ],
            }
        ]
    }
    paths = [request.url.path for request in seen_requests]
    assert paths == [
        "/alerts/active",
        "/points/60.5544,-151.2583",
        "/gridpoints/AFC/145,136/stations",
        "/stations/PAEN/observations/latest",
        "/gridpoints/AFC/145,136/forecast",
        "/gridpoints/AFC/145,136/forecast/hourly",
        "/gridpoints/AFC/145,136",
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
            "advisory_explanation": "",
            "fishing_impact": "",
        },
        {
            "title": "Hydrologic Outlook",
            "severity": "watch",
            "summary": "Rises are possible next week.",
            "source": "NWS Alaska Pacific River Forecast Center",
            "advisory_explanation": "",
            "fishing_impact": "",
        },
        {
            "title": "Special Weather Statement",
            "severity": "info",
            "summary": "",
            "source": "nws",
            "advisory_explanation": "",
            "fishing_impact": "",
        },
    ]


def test_parse_nws_weather_extracts_rain_wind_temperature_and_forecast_text() -> None:
    payload = json.dumps(
        {
            "locations": [
                {
                    "location": "Kenai,AK",
                    "forecast_grid": {
                        "properties": {
                            "quantitativePrecipitation": {
                                "uom": "wmoUnit:mm",
                                "values": [
                                    {
                                        "validTime": "2026-07-22T12:00:00+00:00/PT6H",
                                        "value": 2.54,
                                    },
                                    {
                                        "validTime": "2026-07-22T18:00:00+00:00/PT6H",
                                        "value": 5.08,
                                    },
                                ],
                            },
                            "windSpeed": {
                                "uom": "wmoUnit:km_h-1",
                                "values": [
                                    {
                                        "validTime": "2026-07-22T12:00:00+00:00/PT1H",
                                        "value": 32.1869,
                                    }
                                ],
                            },
                        }
                    },
                    "hourly_forecast": {
                        "properties": {
                            "periods": [
                                {
                                    "startTime": "2026-07-22T12:00:00+00:00",
                                    "temperature": 58,
                                    "temperatureUnit": "F",
                                    "windSpeed": "10 mph",
                                    "windDirection": "S",
                                    "shortForecast": "Chance Rain Showers",
                                    "detailedForecast": "A chance of rain showers before noon.",
                                    "probabilityOfPrecipitation": {
                                        "unitCode": "wmoUnit:percent",
                                        "value": 40,
                                    },
                                }
                            ]
                        }
                    },
                }
            ]
        }
    )

    weather = parse_nws_weather(payload)

    assert len(weather) == 1
    assert weather[0].location == "Kenai,AK"
    assert weather[0].recent_rain_inches_24h == 0.3
    assert weather[0].wind_mph == 20.0
    assert weather[0].temperature_f == 58
    assert weather[0].wind_direction == "S"
    assert weather[0].short_forecast == "Chance Rain Showers"
    assert weather[0].precipitation_probability == 40


def test_parse_nws_weather_extracts_latest_station_observation() -> None:
    payload = json.dumps(
        {
            "locations": [
                {
                    "location": "Kenai,AK",
                    "latest_observations": [
                        {
                            "station_id": "PAEN",
                            "station_name": "Kenai Municipal Airport",
                            "observation": {
                                "properties": {
                                    "timestamp": "2026-05-02T17:30:00+00:00",
                                    "temperature": {
                                        "unitCode": "wmoUnit:degC",
                                        "value": 6.0,
                                    },
                                    "windSpeed": {
                                        "unitCode": "wmoUnit:km_h-1",
                                        "value": 35.186,
                                    },
                                    "windDirection": {
                                        "unitCode": "wmoUnit:degree_(angle)",
                                        "value": 200,
                                    },
                                    "precipitationLastHour": {
                                        "unitCode": "wmoUnit:mm",
                                        "value": 2.54,
                                    },
                                    "textDescription": "Clear and Windy",
                                }
                            },
                        }
                    ],
                }
            ]
        }
    )

    weather = parse_nws_weather(payload)

    assert len(weather) == 1
    assert weather[0].location == "Kenai Municipal Airport"
    assert weather[0].observed_at.isoformat() == "2026-05-02T17:30:00+00:00"
    assert weather[0].temperature_f == 42.8
    assert weather[0].wind_mph == 21.9
    assert weather[0].wind_direction == "200"
    assert weather[0].recent_rain_inches_24h == 0.1
    assert weather[0].short_forecast == "Clear and Windy"
    assert weather[0].source == "nws:PAEN"
