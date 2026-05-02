import httpx

from kenai_engine.config import Settings
from kenai_engine.sources.usgs import UsgsAdapter, parse_usgs_payload


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
    assert params["parameterCd"] == "00060,00065,00010"
    assert params["siteStatus"] == "active"


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
    assert observations[0].parameter_name == "Discharge, cubic feet per second"
    assert observations[0].value == 1230
    assert observations[0].unit == "ft3/s"
    assert observations[0].qualifiers == ["P"]
