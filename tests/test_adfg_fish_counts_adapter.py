import httpx

from kenai_engine.config import Settings
from kenai_engine.sources.adfg_fish_counts import AdfgFishCountsAdapter, parse_fish_counts


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


def test_adfg_fish_counts_adapter_fetches_configured_page(tmp_path) -> None:
    seen_urls: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(request.url)
        return httpx.Response(200, text="<html><body>fish counts</body></html>")

    client = httpx.Client(transport=httpx.MockTransport(handler))

    snapshot = AdfgFishCountsAdapter(
        _settings(tmp_path),
        source_url="https://example.test/adfg/counts",
        client=client,
    ).fetch()

    assert snapshot.source == "adfg_fish_counts"
    assert snapshot.payload == "<html><body>fish counts</body></html>"
    assert seen_urls == [httpx.URL("https://example.test/adfg/counts")]


def test_parse_fish_counts_extracts_simple_html_table_records() -> None:
    html = """
    <table>
      <thead>
        <tr>
          <th>Species</th>
          <th>Location</th>
          <th>Count</th>
          <th>Observation Date</th>
          <th>Source URL</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>Chinook salmon</td>
          <td>Kenai River sonar</td>
          <td>1,234</td>
          <td>2026-07-14</td>
          <td><a href="https://example.test/report">daily report</a></td>
        </tr>
      </tbody>
    </table>
    """

    counts = parse_fish_counts(html)

    assert counts == [
        {
            "species": "Chinook salmon",
            "location": "Kenai River sonar",
            "count": 1234,
            "observation_date": "2026-07-14",
            "source_url": "https://example.test/report",
        }
    ]


def test_parse_fish_counts_extracts_json_payload_records() -> None:
    payload = """
    {
      "fish_counts": [
        {
          "species": "Sockeye",
          "location": "Russian River weir",
          "count": "2,345",
          "observation_date": "2026-06-18",
          "source_url": "https://example.test/json"
        }
      ]
    }
    """

    counts = parse_fish_counts(payload)

    assert counts == [
        {
            "species": "Sockeye",
            "location": "Russian River weir",
            "count": 2345,
            "observation_date": "2026-06-18",
            "source_url": "https://example.test/json",
        }
    ]
