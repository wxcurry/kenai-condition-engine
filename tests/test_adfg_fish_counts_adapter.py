from datetime import date
from pathlib import Path

import httpx

from kenai_engine.config import Settings
from kenai_engine.sources.adfg_fish_counts import (
    AdfgFishCountsAdapter,
    default_fish_count_urls,
    parse_fish_counts,
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


def test_adfg_fish_counts_adapter_fetches_all_configured_count_pages(tmp_path) -> None:
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(200, text=f"<html>{request.url.path}</html>")

    client = httpx.Client(transport=httpx.MockTransport(handler))

    snapshot = AdfgFishCountsAdapter(
        _settings(tmp_path),
        source_url=[
            "https://example.test/adfg/kenai",
            "https://example.test/adfg/russian",
        ],
        client=client,
    ).fetch()

    assert seen_urls == [
        "https://example.test/adfg/kenai",
        "https://example.test/adfg/russian",
    ]
    assert "https://example.test/adfg/kenai" in snapshot.payload
    assert "https://example.test/adfg/russian" in snapshot.payload


def test_default_fish_count_urls_use_json_exports_for_kenai_sources() -> None:
    urls = default_fish_count_urls(year=2026)

    assert (
        "https://www.adfg.alaska.gov/sf/FishCounts/index.cfm?"
        "ADFG=export.JSON&countLocationID=72&year=2026,2025,2024,2023,2022&speciesID=411"
    ) in urls
    assert (
        "https://www.adfg.alaska.gov/sf/FishCounts/index.cfm?"
        "ADFG=export.JSON&countLocationID=72&year=2026,2025,2024,2023,2022&speciesID=412"
    ) in urls
    assert (
        "https://www.adfg.alaska.gov/sf/FishCounts/index.cfm?"
        "ADFG=export.JSON&countLocationID=40&year=2026,2025,2024,2023,2022&speciesID=420"
    ) in urls
    assert all("ADFG=export.JSON" in url for url in urls)


def test_default_fish_count_urls_skip_inactive_seasonal_sources() -> None:
    urls = default_fish_count_urls(year=2026, active_on=date(2026, 5, 5))

    assert urls == ()


def test_default_fish_count_urls_include_only_active_seasonal_sources() -> None:
    urls = default_fish_count_urls(year=2026, active_on=date(2026, 7, 22))

    assert all("ADFG=export.JSON" in url for url in urls)
    assert any("countLocationID=40" in url and "speciesID=420" in url for url in urls)
    assert any("countLocationID=13" in url and "speciesID=422" in url for url in urls)
    assert not any("speciesID=411" in url for url in urls)


def test_parse_fish_counts_reads_fixture_records() -> None:
    payload = _fixture("adfg_kenai_sockeye_counts.html")

    counts = parse_fish_counts(payload)

    assert [count["count"] for count in counts] == [35000, 31000, 25000]
    assert all(count["location"] == "Kenai River late-run sockeye" for count in counts)


def test_parse_fish_counts_extracts_actualish_adfg_display_page() -> None:
    payload = _fixture("adfg_actualish_fish_count_page.html")

    counts = parse_fish_counts(payload)

    assert counts[:3] == [
        {
            "species": "Sockeye",
            "location": "Kenai River (late-run sockeye)",
            "count": 35000,
            "observation_date": "2026-07-22",
        },
        {
            "species": "Sockeye",
            "location": "Kenai River (late-run sockeye)",
            "count": 31000,
            "observation_date": "2026-07-21",
        },
        {
            "species": "Sockeye",
            "location": "Kenai River (late-run sockeye)",
            "count": 25000,
            "observation_date": "2026-07-20",
        },
    ]


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


def test_parse_fish_counts_extracts_adfg_columns_data_payload() -> None:
    payload = """
    {
      "COLUMNS": [
        "YEAR",
        "COUNTDATE",
        "FISHCOUNT",
        "SPECIESID",
        "COUNTLOCATIONID",
        "COUNTLOCATION",
        "SPECIES"
      ],
      "DATA": [
        [2026, "07/22/2026", 35000, 420, 40, "Kenai River late-run sockeye", "Sockeye"]
      ]
    }
    """

    counts = parse_fish_counts(payload)

    assert counts == [
        {
            "species": "Sockeye",
            "location": "Kenai River late-run sockeye",
            "count": 35000,
            "observation_date": "2026-07-22",
            "count_location_id": "40",
            "species_id": "420",
            "year": "2026",
        }
    ]


def test_parse_fish_counts_extracts_all_concatenated_adfg_json_exports() -> None:
    payload = """
    <!-- source_url: https://example.test/chinook -->
    {
      "COLUMNS": [
        "YEAR",
        "COUNTDATE",
        "FISHCOUNT",
        "SPECIESID",
        "COUNTLOCATIONID",
        "COUNTLOCATION",
        "SPECIES"
      ],
      "DATA": [
        [2025, "May, 16 2025 00:00:00", 0, 411, 72, "Kenai River (Chinook)", "Chinook - Early Run"]
      ]
    }
    <!-- source_url: https://example.test/sockeye -->
    {
      "COLUMNS": [
        "YEAR",
        "COUNTDATE",
        "FISHCOUNT",
        "SPECIESID",
        "COUNTLOCATIONID",
        "COUNTLOCATION",
        "SPECIES"
      ],
      "DATA": [
        [2025, "July, 01 2025 00:00:00", 1200, 420, 40, "Kenai River (late-run sockeye)", "Sockeye"]
      ]
    }
    """

    counts = parse_fish_counts(payload)

    assert counts == [
        {
            "species": "Chinook - Early Run",
            "location": "Kenai River (Chinook)",
            "count": 0,
            "observation_date": "2025-05-16",
            "count_location_id": "72",
            "species_id": "411",
            "year": "2025",
        },
        {
            "species": "Sockeye",
            "location": "Kenai River (late-run sockeye)",
            "count": 1200,
            "observation_date": "2025-07-01",
            "count_location_id": "40",
            "species_id": "420",
            "year": "2025",
        },
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


def _fixture(name: str) -> str:
    return (Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8")
