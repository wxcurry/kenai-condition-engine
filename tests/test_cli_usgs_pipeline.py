import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from kenai_engine.cli import build_report, normalize, validate
from kenai_engine.config import Settings
from kenai_engine.db import connect, initialize_database
from kenai_engine.storage.normalized_records import list_normalized_records, save_normalized_record
from kenai_engine.storage.raw_snapshots import save_raw_snapshot
from kenai_engine.storage.source_health import list_latest_source_health, save_source_health


def test_normalize_converts_latest_usgs_snapshot_to_records(tmp_path) -> None:
    settings = _settings(tmp_path)
    payload = _usgs_payload()

    with connect(settings.db_path) as connection:
        initialize_database(connection)
        save_raw_snapshot(connection, "usgs", payload, "2026-05-02T12:00:00+00:00")

    normalize(settings)
    normalize(settings)

    with connect(settings.db_path) as connection:
        rows = list_normalized_records(connection, "usgs_observation")

    assert len(rows) == 1
    stored = json.loads(rows[0]["payload"])
    assert stored["site_id"] == "15266300"
    assert stored["parameter_code"] == "00060"


def test_build_report_includes_latest_usgs_observation_note(tmp_path) -> None:
    settings = _settings(tmp_path)
    with connect(settings.db_path) as connection:
        initialize_database(connection)
        save_raw_snapshot(connection, "usgs", _usgs_payload(), "2026-05-02T12:00:00+00:00")

    normalize(settings)
    build_report(settings)

    report = json.loads((settings.output_dir / "latest.json").read_text(encoding="utf-8"))

    assert "USGS 00060" in report["locations"][0]["notes"][0]
    assert (settings.public_dir / "v1" / "latest.json").exists()


def test_validate_regenerates_invalid_existing_latest_json(tmp_path) -> None:
    settings = _settings(tmp_path)
    settings.output_dir.mkdir(parents=True)
    (settings.output_dir / "latest.json").write_text(
        json.dumps({"schema_version": "1.0.0", "overall_status": "caution"}),
        encoding="utf-8",
    )

    validate(settings)

    report = json.loads((settings.output_dir / "latest.json").read_text(encoding="utf-8"))
    assert report["overall_status"] in {
        "poor",
        "fair",
        "good",
        "excellent",
        "restricted",
        "closed",
        "unknown",
    }


def test_normalize_and_build_report_use_regulations_fish_counts_and_alerts(tmp_path) -> None:
    settings = _settings(tmp_path)
    with connect(settings.db_path) as connection:
        initialize_database(connection)
        save_raw_snapshot(
            connection,
            "adfg_emergency_orders",
            """
            <section>
              <a href="/orders/closure">Emergency Order 2-KS-9-26</a>
              <p>Kenai River sport fishing is closed.</p>
            </section>
            """,
            "2026-05-02T12:00:00+00:00",
        )
        save_raw_snapshot(
            connection,
            "adfg_fish_counts",
            """
            <table>
              <tr><th>Species</th><th>Location</th><th>Count</th><th>Date</th></tr>
              <tr><td>Sockeye</td><td>Kenai sonar</td><td>123</td><td>2026-05-02</td></tr>
            </table>
            """,
            "2026-05-02T12:00:00+00:00",
        )
        save_raw_snapshot(
            connection,
            "nws",
            """
            {
              "locations": [
                {
                  "alerts": {
                    "features": [
                      {
                        "properties": {
                          "event": "Flood Warning",
                          "severity": "Severe",
                          "headline": "Flooding possible",
                          "senderName": "NWS Anchorage"
                        }
                      }
                    ]
                  }
                }
              ]
            }
            """,
            "2026-05-02T12:00:00+00:00",
        )

    normalize(settings)
    build_report(settings)

    report = json.loads((settings.output_dir / "latest.json").read_text(encoding="utf-8"))

    assert report["overall_status"] == "closed"
    assert report["regulations"][0]["status"] == "closed"
    assert report["fish_counts"][0]["count"] == 123
    assert report["alerts"][0]["severity"] == "warning"


def test_normalize_adds_adfg_fishing_reports_as_information_alerts(tmp_path) -> None:
    settings = _settings(tmp_path)
    with connect(settings.db_path) as connection:
        initialize_database(connection)
        save_raw_snapshot(
            connection,
            "adfg_fishing_reports",
            _fixture("adfg_fishing_reports.html"),
            "2026-07-22T12:00:00+00:00",
        )

    normalize(settings)

    with connect(settings.db_path) as connection:
        rows = list_normalized_records(connection, "alert")

    alerts = [json.loads(row["payload"]) for row in rows]
    fishing_report_alert = next(
        alert for alert in alerts if alert["source"] == "adfg_fishing_reports"
    )
    assert fishing_report_alert["severity"] == "info"
    assert fishing_report_alert["title"] == "Northern Kenai Fishing Report"


def test_build_report_filters_stale_irrelevant_fishing_report_alerts(tmp_path) -> None:
    settings = _settings(tmp_path)
    with connect(settings.db_path) as connection:
        initialize_database(connection)
        save_normalized_record(
            connection,
            "alert",
            "2026-07-22T12:00:00+00:00",
            json.dumps(
                {
                    "title": "Southeast Fishing Reports",
                    "severity": "info",
                    "summary": "Old parser artifact mentioning Kenai in page navigation.",
                    "source": "adfg_fishing_reports",
                }
            ),
        )
        save_normalized_record(
            connection,
            "alert",
            "2026-07-22T12:01:00+00:00",
            json.dumps(
                {
                    "title": "Kenai River / Northern Kenai",
                    "severity": "info",
                    "summary": "Current Kenai report.",
                    "source": "adfg_fishing_reports",
                }
            ),
        )

    build_report(settings)

    report = json.loads((settings.output_dir / "latest.json").read_text(encoding="utf-8"))
    titles = [alert["title"] for alert in report["alerts"]]
    assert "Kenai River / Northern Kenai" in titles
    assert "Southeast Fishing Reports" not in titles


def test_build_report_filters_alert_limit_per_source(tmp_path) -> None:
    settings = _settings(tmp_path)
    with connect(settings.db_path) as connection:
        initialize_database(connection)
        save_normalized_record(
            connection,
            "alert",
            "2026-07-22T12:00:00+00:00",
            json.dumps(
                {
                    "title": "Kenai River / Northern Kenai",
                    "severity": "info",
                    "summary": "Current Kenai report.",
                    "source": "adfg_fishing_reports",
                }
            ),
        )
        for index in range(20):
            save_normalized_record(
                connection,
                "alert",
                f"2026-07-22T12:{index + 1:02d}:00+00:00",
                json.dumps(
                    {
                        "title": f"Flood Watch {index}",
                        "severity": "watch",
                        "summary": "NWS alert should not crowd out fishing reports.",
                        "source": "NWS Anchorage",
                    }
                ),
            )

    build_report(settings)

    report = json.loads((settings.output_dir / "latest.json").read_text(encoding="utf-8"))
    titles = [alert["title"] for alert in report["alerts"]]
    assert "Kenai River / Northern Kenai" in titles


def test_build_report_gates_fishing_report_alerts_by_fishing_report_source_health(
    tmp_path,
) -> None:
    settings = _settings(tmp_path)
    with connect(settings.db_path) as connection:
        initialize_database(connection)
        save_normalized_record(
            connection,
            "alert",
            "2026-07-22T12:00:00+00:00",
            json.dumps(
                {
                    "title": "Kenai River / Northern Kenai",
                    "severity": "info",
                    "summary": "Current Kenai report.",
                    "source": "adfg_fishing_reports",
                }
            ),
        )
        save_normalized_record(
            connection,
            "alert",
            "2026-07-22T12:01:00+00:00",
            json.dumps(
                {
                    "title": "Flood Warning",
                    "severity": "warning",
                    "summary": "NWS alert should remain available.",
                    "source": "NWS Anchorage",
                }
            ),
        )
        save_source_health(
            connection,
            source="nws",
            checked_at="2026-07-22T12:02:00+00:00",
            status="ok",
            message="Fetched NWS.",
        )
        save_source_health(
            connection,
            source="adfg_fishing_reports",
            checked_at="2026-07-22T12:02:00+00:00",
            status="error",
            message="Could not normalize latest ADF&G fishing reports snapshot.",
        )

    build_report(settings)

    report = json.loads((settings.output_dir / "latest.json").read_text(encoding="utf-8"))
    titles = [alert["title"] for alert in report["alerts"]]
    assert "Flood Warning" in titles
    assert "Kenai River / Northern Kenai" not in titles


def test_build_report_uses_latest_persisted_source_health(tmp_path) -> None:
    settings = _settings(tmp_path)
    with connect(settings.db_path) as connection:
        initialize_database(connection)
        save_source_health(
            connection,
            source="adfg_emergency_orders",
            checked_at="2026-05-02T12:00:00+00:00",
            status="error",
            message="Fetch timed out.",
        )

    build_report(settings)

    report = json.loads((settings.output_dir / "latest.json").read_text(encoding="utf-8"))

    assert report["regulations"] == []
    assert report["fish_counts"] == []
    assert report["alerts"] == []
    assert report["source_health"][0]["source"] == "adfg_emergency_orders"
    assert report["source_health"][0]["status"] == "failed"
    assert report["source_health"][0]["severity"] == "critical"
    assert report["source_health"][0]["user_title"] == "Regulation source unavailable"
    assert report["warnings"][0]["source"] == "adfg_emergency_orders"


def test_normalize_parser_failure_updates_source_health(tmp_path) -> None:
    settings = _settings(tmp_path)
    checked_at = "2026-05-02T12:00:00+00:00"
    with connect(settings.db_path) as connection:
        initialize_database(connection)
        save_raw_snapshot(connection, "usgs", "{not valid json", checked_at)
        save_source_health(
            connection,
            source="usgs",
            checked_at=checked_at,
            status="ok",
            message="Fetched USGS.",
        )

    normalize(settings)

    with connect(settings.db_path) as connection:
        latest_health = list_latest_source_health(connection)

    usgs_health = next(row for row in latest_health if row["source"] == "usgs")
    assert usgs_health["status"] == "error"
    assert "Could not normalize latest USGS snapshot" in usgs_health["message"]


def test_build_report_ignores_records_for_failed_latest_source_health(tmp_path) -> None:
    settings = _settings(tmp_path)
    with connect(settings.db_path) as connection:
        initialize_database(connection)
        save_normalized_record(
            connection,
            "fish_count",
            "2026-05-01",
            json.dumps(
                {
                    "species": "Sockeye",
                    "location": "Kenai sonar",
                    "count": 12345,
                    "observation_date": "2026-05-01",
                }
            ),
        )
        save_source_health(
            connection,
            source="adfg_fish_counts",
            checked_at="2026-05-02T12:00:00+00:00",
            status="error",
            message="Could not normalize latest ADF&G fish counts snapshot.",
        )

    build_report(settings)

    report = json.loads((settings.output_dir / "latest.json").read_text(encoding="utf-8"))

    assert report["fish_counts"] == []
    fish_count_health = next(
        health for health in report["source_health"] if health["source"] == "adfg_fish_counts"
    )
    assert fish_count_health["status"] == "failed"


def test_normalize_and_build_report_use_weather_tide_and_flow_statistics(tmp_path) -> None:
    settings = _settings(tmp_path)
    now = datetime.now(UTC)
    low_tide = (now - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M")
    high_tide = (now + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M")
    with connect(settings.db_path) as connection:
        initialize_database(connection)
        save_raw_snapshot(
            connection,
            "usgs",
            _fixture("usgs_kenai_gages.json"),
            "2026-07-22T12:00:00+00:00",
        )
        save_raw_snapshot(
            connection,
            "usgs_statistics",
            json.dumps(
                {
                    "value": {
                        "timeSeries": [
                            {
                                "sourceInfo": {"siteCode": [{"value": "15266300"}]},
                                "variable": {"variableCode": [{"value": "00060"}]},
                                "values": [
                                    {
                                        "value": [
                                            {
                                                "month_nu": str(now.month),
                                                "day_nu": str(now.day),
                                                "p25_va": "2500",
                                                "p50_va": "4000",
                                                "p75_va": "6000",
                                                "p90_va": "7500",
                                                "p95_va": "8300",
                                            }
                                        ]
                                    }
                                ],
                            }
                        ]
                    }
                }
            ),
            "2026-07-22T12:00:00+00:00",
        )
        save_raw_snapshot(
            connection,
            "nws",
            json.dumps(
                {
                    "locations": [
                        {
                            "location": "Kenai,AK",
                            "alerts": {"features": []},
                            "forecast_grid": {
                                "properties": {
                                    "quantitativePrecipitation": {
                                        "values": [{"value": 2.54}]
                                    },
                                    "windSpeed": {"values": [{"value": 16.0934}]},
                                }
                            },
                        }
                    ]
                }
            ),
            "2026-07-22T12:00:00+00:00",
        )
        save_raw_snapshot(
            connection,
            "noaa_tides",
            json.dumps(
                {
                    "predictions": [
                        {"t": low_tide, "v": "2.1", "type": "L"},
                        {"t": high_tide, "v": "20.4", "type": "H"},
                    ]
                }
            ),
            "2026-07-22T12:00:00+00:00",
        )
        for source in ("usgs", "usgs_statistics", "nws", "noaa_tides"):
            save_source_health(
                connection,
                source=source,
                checked_at="2026-07-22T12:00:00+00:00",
                status="ok",
                message=f"Fetched {source}.",
            )

    normalize(settings)
    build_report(settings)

    report = json.loads((settings.output_dir / "latest.json").read_text(encoding="utf-8"))
    notes = " ".join(report["locations"][0]["notes"])

    assert "USGS flow percentile" in notes
    assert "NWS forecast rain" in notes
    assert "NWS wind" in notes
    assert "NOAA tide stage" in notes


def _settings(tmp_path) -> Settings:
    return Settings(
        user_agent="test-agent",
        db_path=tmp_path / "db.sqlite3",
        output_dir=tmp_path / "reports",
        public_dir=tmp_path / "public",
        raw_dir=tmp_path / "raw",
        usgs_site_ids=["15266300"],
        nws_locations=["Kenai,AK"],
        fetch_timeout_seconds=1,
    )


def _usgs_payload() -> str:
    return """
    {
      "value": {
        "timeSeries": [
          {
            "sourceInfo": {
              "siteName": "KENAI RIVER AT COOPER LANDING AK",
              "siteCode": [{"value": "15266300"}]
            },
            "variable": {
              "variableCode": [{"value": "00060"}],
              "variableName": "Discharge, cubic feet per second",
              "unit": {"unitCode": "ft3/s"}
            },
            "values": [
              {
                "value": [
                  {
                    "value": "1230",
                    "dateTime": "2026-05-02T12:00:00.000-08:00",
                    "qualifiers": ["P"]
                  }
                ]
              }
            ]
          }
        ]
      }
    }
    """


def _fixture(name: str) -> str:
    return (Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8")
