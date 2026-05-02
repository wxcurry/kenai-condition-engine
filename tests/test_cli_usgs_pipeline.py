import json

from kenai_engine.cli import build_report, normalize
from kenai_engine.config import Settings
from kenai_engine.db import connect, initialize_database
from kenai_engine.storage.normalized_records import list_normalized_records
from kenai_engine.storage.raw_snapshots import save_raw_snapshot


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
