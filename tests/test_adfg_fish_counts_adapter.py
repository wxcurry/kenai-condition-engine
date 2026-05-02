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


def test_parse_fish_counts_extracts_realistic_adfg_table_rows() -> None:
    html = """
    <table>
      <tr>
        <th>Species</th>
        <th>Site</th>
        <th>Passage</th>
        <th>Report Date</th>
      </tr>
      <tr>
        <td>Sockeye Salmon</td>
        <td>Russian River Weir</td>
        <td>12,345</td>
        <td>06/18/2026</td>
      </tr>
      <tr>
        <td>Chinook Salmon</td>
        <td>Deshka River</td>
        <td>999</td>
        <td>06/18/2026</td>
      </tr>
    </table>
    """

    counts = parse_fish_counts(html)

    assert counts == [
        {
            "species": "Sockeye Salmon",
            "location": "Russian River Weir",
            "count": 12345,
            "observation_date": "2026-06-18",
        }
    ]


def test_parse_fish_counts_uses_cumulative_and_skips_bad_dates() -> None:
    html = """
    <table>
      <thead>
        <tr>
          <th>Species</th>
          <th>Location</th>
          <th>Cumulative</th>
          <th>Date</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>Coho</td>
          <td>Kasilof River sonar</td>
          <td>4,001</td>
          <td>2026-08-01</td>
        </tr>
        <tr>
          <td>Sockeye</td>
          <td>Kenai River sonar</td>
          <td>3,500</td>
          <td>not posted</td>
        </tr>
        <tr>
          <td>Sockeye</td>
          <td>Russian River Weir</td>
          <td>2,100</td>
          <td></td>
        </tr>
      </tbody>
    </table>
    """

    counts = parse_fish_counts(html)

    assert counts == [
        {
            "species": "Coho",
            "location": "Kasilof River sonar",
            "count": 4001,
            "observation_date": "2026-08-01",
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


def test_parse_fish_counts_extracts_embedded_json_records() -> None:
    payload = """
    <html>
      <body>
        <script>
          window.fishCounts = [
            {
              "Species": "Sockeye",
              "Site": "Kenai River Late Run Sonar",
              "Passage": "1,010",
              "Report Date": "2026-07-01"
            },
            {
              "Species": "Sockeye",
              "Site": "Copper River",
              "Passage": "8,888",
              "Report Date": "2026-07-01"
            }
          ];
        </script>
      </body>
    </html>
    """

    counts = parse_fish_counts(payload)

    assert counts == [
        {
            "species": "Sockeye",
            "location": "Kenai River Late Run Sonar",
            "count": 1010,
            "observation_date": "2026-07-01",
        }
    ]
