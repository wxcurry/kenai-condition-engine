import httpx

from kenai_engine.config import Settings
from kenai_engine.sources.usgs import (
    EXPANDED_USGS_PARAMETER_CODES,
    USGS_LATEST_CONTINUOUS_URL,
    UsgsAdapter,
    UsgsModernAdapter,
    UsgsStatisticsAdapter,
    calculate_flow_percentile,
    classify_usgs_trend,
    normalize_monitoring_location_id,
    parse_usgs_payload,
    parse_usgs_statistics_payload,
)


def test_usgs_adapter_fetches_instantaneous_values_with_expected_params(tmp_path) -> None:
    settings = Settings(
        user_agent="test-agent",
        db_path=tmp_path / "db.sqlite3",
        output_dir=tmp_path / "reports",
        raw_dir=tmp_path / "raw",
        usgs_site_ids=["15266300"],
        nws_locations=["Kenai,AK"],
        fetch_timeout_seconds=1,
    )
    seen_urls: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(request.url)
        return httpx.Response(200, json={"value": {"timeSeries": []}})

    client = httpx.Client(transport=httpx.MockTransport(handler))

    snapshot = UsgsAdapter(settings, client=client).fetch()

    assert snapshot.source == "usgs"
    assert seen_urls
    params = dict(seen_urls[0].params.multi_items())
    assert seen_urls[0].host == "waterservices.usgs.gov"
    assert params["format"] == "json"
    assert params["sites"] == "15266300"
    assert params["parameterCd"] == ",".join(EXPANDED_USGS_PARAMETER_CODES)
    assert params["siteStatus"] == "all"


def test_usgs_modern_adapter_fetches_latest_continuous_items_with_expected_params(
    tmp_path,
) -> None:
    settings = Settings(
        user_agent="test-agent",
        db_path=tmp_path / "db.sqlite3",
        output_dir=tmp_path / "reports",
        raw_dir=tmp_path / "raw",
        usgs_site_ids=["15266300"],
        nws_locations=["Kenai,AK"],
        fetch_timeout_seconds=1,
    )
    seen_urls: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(request.url)
        return httpx.Response(200, json={"type": "FeatureCollection", "features": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))

    snapshot = UsgsModernAdapter(settings, client=client).fetch()

    assert snapshot.source == "usgs"
    assert seen_urls
    assert str(seen_urls[0].copy_with(query=None)) == USGS_LATEST_CONTINUOUS_URL
    params = dict(seen_urls[0].params.multi_items())
    assert params["f"] == "json"
    assert params["monitoring_location_id"] == "USGS-15266300"
    assert params["parameter_code"] == ",".join(EXPANDED_USGS_PARAMETER_CODES)


def test_normalize_monitoring_location_id_accepts_nwis_and_ogc_forms() -> None:
    assert normalize_monitoring_location_id("10172640") == ("USGS-10172640", "10172640")
    assert normalize_monitoring_location_id("USGS-10172640") == ("USGS-10172640", "10172640")


def test_parse_usgs_payload_returns_observations() -> None:
    payload = """
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

    observations = parse_usgs_payload(payload)

    assert len(observations) == 1
    assert observations[0].site_id == "15266300"
    assert observations[0].site_name == "KENAI RIVER AT COOPER LANDING AK"
    assert observations[0].parameter_code == "00060"
    assert observations[0].parameter_name == "discharge"
    assert observations[0].value == 1230
    assert observations[0].unit == "ft3/s"
    assert observations[0].qualifiers == ["P"]


def test_parse_usgs_payload_reads_latest_continuous_geojson_features() -> None:
    payload = """
    {
      "type": "FeatureCollection",
      "features": [
        {
          "type": "Feature",
          "geometry": {"type": "Point", "coordinates": [-149.9, 60.5]},
          "properties": {
            "monitoring_location_id": "USGS-15266300",
            "monitoring_location_name": "KENAI R AT SOLDOTNA AK",
            "parameter_code": "00060",
            "parameter_name": "Discharge",
            "time": "2026-05-02T17:00:00Z",
            "value": 593,
            "unit_of_measure": "ft3/s",
            "approval_status": "Provisional"
          }
        }
      ]
    }
    """

    observations = parse_usgs_payload(payload)

    assert len(observations) == 1
    assert observations[0].site_id == "15266300"
    assert observations[0].monitoring_location_id == "USGS-15266300"
    assert observations[0].site_name == "KENAI R AT SOLDOTNA AK"
    assert observations[0].parameter_code == "00060"
    assert observations[0].parameter_name == "discharge"
    assert observations[0].value == 593
    assert observations[0].unit == "ft3/s"
    assert observations[0].observed_at.isoformat() == "2026-05-02T17:00:00+00:00"
    assert observations[0].qualifiers == ["Provisional"]


def test_parse_usgs_payload_maps_expanded_parameters() -> None:
    payload = """
    {
      "value": {
        "timeSeries": [
          {
            "sourceInfo": {
              "siteName": "KENAI RIVER AT COOPER LANDING AK",
              "siteCode": [{"value": "USGS:10172640"}]
            },
            "variable": {
              "variableCode": [{"value": "63680"}],
              "variableName": "Turbidity, water, FNU",
              "unit": {"unitCode": "FNU"}
            },
            "values": [{"value": [{"value": "4.2", "dateTime": "2026-05-02T12:00:00Z"}]}]
          },
          {
            "sourceInfo": {
              "siteName": "KENAI RIVER AT COOPER LANDING AK",
              "siteCode": [{"value": "10172640"}]
            },
            "variable": {
              "variableCode": [{"value": "00300"}],
              "variableName": "Dissolved oxygen, water, unfiltered, milligrams per liter",
              "unit": {"unitCode": "mg/l"}
            },
            "values": [{"value": [{"value": "10.5", "dateTime": "2026-05-02T12:00:00Z"}]}]
          }
        ]
      }
    }
    """

    observations = parse_usgs_payload(payload)

    assert [observation.site_id for observation in observations] == ["10172640", "10172640"]
    assert [observation.monitoring_location_id for observation in observations] == [
        "USGS-10172640",
        "USGS-10172640",
    ]
    assert [observation.parameter_name for observation in observations] == [
        "turbidity",
        "dissolved_oxygen",
    ]


def test_classify_usgs_trend_protects_against_single_noisy_measurement() -> None:
    latest_window = parse_usgs_payload(
        """
        {
          "value": {
            "timeSeries": [
              {
                "sourceInfo": {"siteName": "KENAI", "siteCode": [{"value": "10172640"}]},
                "variable": {
                  "variableCode": [{"value": "00065"}],
                  "variableName": "Gage height",
                  "unit": {"unitCode": "ft"}
                },
                "values": [
                  {
                    "value": [
                      {"value": "10.00", "dateTime": "2026-05-02T10:00:00Z"},
                      {"value": "10.03", "dateTime": "2026-05-02T11:00:00Z"},
                      {"value": "10.04", "dateTime": "2026-05-02T12:00:00Z"},
                      {"value": "10.80", "dateTime": "2026-05-02T12:15:00Z"}
                    ]
                  }
                ]
              }
            ]
          }
        }
        """
    )

    trend = classify_usgs_trend(latest_window, parameter_code="00065")

    assert trend["classification"] == "stable"
    assert trend["sample_count"] == 4
    assert trend["window_minutes"] == 135


def test_usgs_statistics_adapter_fetches_daily_discharge_statistics(tmp_path) -> None:
    settings = Settings(
        user_agent="test-agent",
        db_path=tmp_path / "db.sqlite3",
        output_dir=tmp_path / "reports",
        raw_dir=tmp_path / "raw",
        usgs_site_ids=["15266300"],
        nws_locations=["Kenai,AK"],
        fetch_timeout_seconds=1,
    )
    seen_urls: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(request.url)
        return httpx.Response(200, json={"value": {"timeSeries": []}})

    client = httpx.Client(transport=httpx.MockTransport(handler))

    snapshot = UsgsStatisticsAdapter(settings, client=client).fetch()

    assert snapshot.source == "usgs_statistics"
    params = dict(seen_urls[0].params.multi_items())
    assert seen_urls[0].host == "waterservices.usgs.gov"
    assert params["statReportType"] == "daily"
    assert params["parameterCd"] == "00060"
    assert params["sites"] == "15266300"
    assert params["format"] == "rdb"
    assert params["statType"] == "P25,P50,P75,P90,P95"


def test_parse_usgs_statistics_payload_extracts_percentile_classes() -> None:
    payload = """
    {
      "value": {
        "timeSeries": [
          {
            "sourceInfo": {"siteCode": [{"value": "15266300"}]},
            "variable": {
              "variableCode": [{"value": "00060"}],
              "unit": {"unitCode": "ft3/s"}
            },
            "values": [
              {
                "value": [
                  {
                    "month_nu": "7",
                    "day_nu": "22",
                    "p25_va": "2500",
                    "p50_va": "4000",
                    "p75_va": "6000",
                    "p90_va": "7500",
                    "p95_va": "8300"
                  }
                ]
              }
            ]
          }
        ]
      }
    }
    """

    statistics = parse_usgs_statistics_payload(payload)

    assert len(statistics) == 1
    assert statistics[0].site_id == "15266300"
    assert statistics[0].month == 7
    assert statistics[0].day == 22
    assert statistics[0].p50 == 4000


def test_parse_usgs_statistics_payload_extracts_rdb_percentile_rows() -> None:
    payload = "\n".join(
        [
            "# USGS statistics",
            "agency_cd\tsite_no\tparameter_cd\tloc_web_ds\tdd_nu\tmonth_nu\tday_nu\tp25_va\tp50_va\tp75_va\tp90_va\tp95_va",
            "5s\t15s\t5s\t20s\t5s\t2n\t2n\t10n\t10n\t10n\t10n\t10n",
            "USGS\t15266300\t00060\t\t01\t7\t22\t2500\t4000\t6000\t7500\t8300",
        ]
    )

    statistics = parse_usgs_statistics_payload(payload)

    assert len(statistics) == 1
    assert statistics[0].site_id == "15266300"
    assert statistics[0].month == 7
    assert statistics[0].day == 22
    assert statistics[0].p95 == 8300


def test_calculate_flow_percentile_interpolates_from_daily_statistics() -> None:
    statistic = parse_usgs_statistics_payload(
        """
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
                        "month_nu": "7",
                        "day_nu": "22",
                        "p25_va": "2500",
                        "p50_va": "4000",
                        "p75_va": "6000",
                        "p90_va": "7500",
                        "p95_va": "8300"
                      }
                    ]
                  }
                ]
              }
            ]
          }
        }
        """
    )[0]

    assert calculate_flow_percentile(4000, statistic) == 50
    assert calculate_flow_percentile(6750, statistic) == 82.5
