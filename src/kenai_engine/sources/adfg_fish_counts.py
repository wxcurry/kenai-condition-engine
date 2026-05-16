"""ADFG fish counts source adapter."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup

from kenai_engine.config import Settings
from kenai_engine.seasonal_sources import active_fish_count_runs
from kenai_engine.sources.usgs import RawSnapshot
from kenai_engine.utils.http import build_http_client
from kenai_engine.utils.time import utc_now

ADFG_FISH_COUNTS_URL = "https://www.adfg.alaska.gov/sf/FishCounts/"
ADFG_FISH_COUNTS_EXPORT_URL = "https://www.adfg.alaska.gov/sf/FishCounts/index.cfm"
KENAI_CHINOOK_COUNT_LOCATION_ID = 72
KENAI_CHINOOK_EARLY_RUN_SPECIES_ID = 411
KENAI_CHINOOK_LATE_RUN_SPECIES_ID = 412
KENAI_LATE_RUN_SOCKEYE_COUNT_LOCATION_ID = 40
KENAI_LATE_RUN_SOCKEYE_SPECIES_ID = 420
RUSSIAN_RIVER_SOCKEYE_COUNT_LOCATION_ID = 13
RUSSIAN_RIVER_EARLY_SOCKEYE_SPECIES_ID = 421
RUSSIAN_RIVER_LATE_SOCKEYE_SPECIES_ID = 422
DEFAULT_FISH_COUNT_SOURCES = tuple(
    (run.count_location_id, run.species_id) for run in active_fish_count_runs(None)
)
KENAI_RELEVANT_TERMS = ("kenai", "russian", "kasilof")


class AdfgFishCountsAdapter:
    """ADFG fish counts adapter."""

    source_name = "adfg_fish_counts"

    def __init__(
        self,
        settings: Settings,
        *,
        source_url: str | list[str] | tuple[str, ...] | None = None,
        active_on: date | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings
        if source_url is None:
            self._source_urls = default_fish_count_urls(active_on=active_on or utc_now().date())
        elif isinstance(source_url, str):
            self._source_urls = (source_url,)
        else:
            self._source_urls = tuple(source_url)
        self._client = client

    def fetch(self) -> RawSnapshot:
        client = self._client or build_http_client(self._settings)
        should_close = self._client is None
        try:
            pages: list[str] = []
            for source_url in self._source_urls:
                response = client.get(source_url)
                response.raise_for_status()
                if len(self._source_urls) == 1:
                    pages.append(response.text)
                else:
                    pages.append(f"<!-- source_url: {source_url} -->\n{response.text}")
            payload = "\n".join(pages)
        finally:
            if should_close:
                client.close()

        return RawSnapshot(
            source=self.source_name,
            fetched_at=utc_now().isoformat(),
            payload=payload,
        )


def default_fish_count_urls(
    *,
    year: int | None = None,
    active_on: date | None = None,
) -> tuple[str, ...]:
    """Build default ADFG JSON export URLs for Kenai-relevant fish count sources."""

    return tuple(
        fish_count_export_url(run.count_location_id, run.species_id, year=year)
        for run in active_fish_count_runs(active_on)
    )


def fish_count_export_url(
    count_location_id: int,
    species_id: int,
    *,
    year: int | None = None,
    years: Iterable[int] | None = None,
) -> str:
    """Build an ADFG FishCounts JSON export URL."""

    selected_years = tuple(years) if years is not None else _default_year_window(year)
    year_param = ",".join(str(selected_year) for selected_year in selected_years)
    return (
        f"{ADFG_FISH_COUNTS_EXPORT_URL}?"
        f"ADFG=export.JSON&countLocationID={count_location_id}"
        f"&year={year_param}&speciesID={species_id}"
    )


def parse_fish_counts(payload: str, *, relevant_only: bool = True) -> list[dict[str, object]]:
    """Extract simple fish count records from JSON or HTML fixtures."""

    json_counts = _parse_json_counts(payload)
    counts = json_counts if json_counts else _parse_html_table_counts(payload)
    if not counts:
        counts = _parse_adfg_display_counts(payload)
    if relevant_only:
        return [record for record in counts if _is_kenai_relevant(record)]
    return counts


def _parse_json_counts(payload: str) -> list[dict[str, object]]:
    counts: list[dict[str, object]] = []
    for document in _load_json_documents(payload):
        rows = _extract_json_rows(document)
        for row in rows:
            if isinstance(row, dict):
                record = _normalize_record(row)
                if record:
                    counts.append(record)
    return counts


def _load_json_document(payload: str) -> object | None:
    return next(iter(_load_json_documents(payload)), None)


def _load_json_documents(payload: str) -> list[object]:
    try:
        return [json.loads(payload)]
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    documents: list[object] = []
    position = 0
    while match := re.search(r"[\[{]", payload[position:]):
        start = position + match.start()
        try:
            document, end = decoder.raw_decode(payload[start:])
        except json.JSONDecodeError:
            position = start + 1
            continue
        if _extract_json_rows(document):
            documents.append(document)
            position = start + end
        else:
            position = start + 1
    return documents


def _extract_json_rows(document: object) -> list[object]:
    if isinstance(document, list):
        return document
    if not isinstance(document, dict):
        return []

    columns = document.get("COLUMNS") or document.get("columns")
    data = document.get("DATA") or document.get("data")
    if isinstance(columns, list) and isinstance(data, list):
        normalized_columns = [str(column).lower() for column in columns]
        rows: list[object] = []
        for values in data:
            if not isinstance(values, list):
                continue
            rows.append(
                {
                    normalized_columns[index]: values[index]
                    for index in range(min(len(normalized_columns), len(values)))
                }
            )
        return rows

    for key in ("fish_counts", "fishCounts", "counts", "data"):
        rows = document.get(key)
        if isinstance(rows, list):
            return rows

    for value in document.values():
        rows = _extract_json_rows(value)
        if rows:
            return rows
    return []


def _parse_html_table_counts(html: str) -> list[dict[str, object]]:
    soup = BeautifulSoup(html, "lxml")
    counts: list[dict[str, object]] = []

    for table in soup.select("table"):
        header_row = table.select_one("tr:has(th)")
        if header_row is None:
            continue
        headers = [_canonical_header(cell.get_text(" ", strip=True)) for cell in header_row("th")]
        if not headers:
            continue

        for row in table.select("tr"):
            cells = row.find_all("td")
            if not cells:
                continue
            raw_record: dict[str, Any] = {}
            for index, cell in enumerate(cells):
                if index >= len(headers) or not headers[index]:
                    continue
                key = headers[index]
                link = cell.find("a", href=True)
                raw_record[key] = link["href"] if key == "source_url" and link else cell.get_text(
                    " ", strip=True
                )
            record = _normalize_record(raw_record)
            if record:
                counts.append(record)

    return counts


def _parse_adfg_display_counts(html: str) -> list[dict[str, object]]:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)
    location_match = re.search(r"\bLocation:\s*(?P<location>.*?)\s+Species:", text, re.IGNORECASE)
    species_match = re.search(
        r"\bSpecies:\s*(?P<species>.*?)\s+.*?\bfor\s+(?P<year>\d{4})\b",
        text,
        re.IGNORECASE,
    )
    if location_match is None or species_match is None:
        return []

    location = location_match.group("location").strip()
    species = species_match.group("species").strip()
    year = int(species_match.group("year"))
    counts: list[dict[str, object]] = []
    row_pattern = re.compile(
        r"\b(?P<month>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[-/](?P<day>\d{1,2})\s+"
        r"(?P<count>-|[\d,]+)\s+[\d,]+",
        re.IGNORECASE,
    )
    for match in row_pattern.finditer(text):
        count = _count_value(match.group("count"))
        if count is None:
            continue
        month = _month_number(match.group("month"))
        day = int(match.group("day"))
        counts.append(
            {
                "species": species,
                "location": location,
                "count": count,
                "observation_date": f"{year:04d}-{month:02d}-{day:02d}",
            }
        )
    return counts


def _normalize_record(row: dict[str, Any]) -> dict[str, object]:
    normalized_row = _canonicalize_row(row)
    species = _string_value(normalized_row, "species")
    location = _string_value(normalized_row, "location")
    count = _count_value(normalized_row.get("count"))
    observation_date = _date_value(normalized_row.get("observation_date"))
    if not species or not location or count is None or count < 0 or observation_date is None:
        return {}

    record: dict[str, object] = {
        "species": species,
        "location": location,
        "count": count,
        "observation_date": observation_date,
    }
    daily_count = _count_value(normalized_row.get("daily_count"))
    if daily_count is not None and daily_count >= 0:
        record["daily_count"] = daily_count
    cumulative_count = _count_value(normalized_row.get("cumulative_count"))
    if cumulative_count is not None and cumulative_count >= 0:
        record["cumulative_count"] = cumulative_count
    for optional_key in ("count_location_id", "species_id", "method", "year"):
        optional_value = normalized_row.get(optional_key)
        if optional_value not in (None, ""):
            record[optional_key] = str(optional_value)
    source_url = _string_value(normalized_row, "source_url")
    if source_url:
        record["source_url"] = source_url
    return record


def _canonicalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        canonical_key = _canonical_header(str(key))
        if canonical_key:
            normalized[canonical_key] = value
    return normalized


def _canonical_header(header: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", header.lower()).strip("_")
    aliases = {
        "date": "observation_date",
        "observed": "observation_date",
        "observation_date": "observation_date",
        "report_date": "observation_date",
        "countdate": "observation_date",
        "site": "location",
        "countlocation": "location",
        "passage": "count",
        "fishcount": "count",
        "daily_count": "daily_count",
        "cumulative": "count",
        "cumulative_count": "cumulative_count",
        "countlocationid": "count_location_id",
        "speciesid": "species_id",
        "method": "method",
        "year": "year",
        "source": "source_url",
        "source_url": "source_url",
        "url": "source_url",
    }
    if normalized in {
        "species",
        "location",
        "count",
        "daily_count",
        "cumulative_count",
        "count_location_id",
        "species_id",
        "method",
        "year",
    }:
        return normalized
    return aliases.get(normalized, "")


def _string_value(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    return value.strip() if isinstance(value, str) else ""


def _count_value(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if not isinstance(value, str):
        return None
    normalized = value.replace(",", "").strip()
    if not re.fullmatch(r"-?\d+(\.0+)?", normalized):
        return None
    return int(float(normalized))


def _date_value(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None

    iso_match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})(?:[T ].*)?", text)
    if iso_match:
        return iso_match.group(1)

    for date_format in ("%m/%d/%Y", "%m/%d/%y", "%B, %d %Y %H:%M:%S", "%b, %d %Y %H:%M:%S"):
        try:
            return datetime.strptime(text, date_format).date().isoformat()
        except ValueError:
            continue
    return None


def _default_year_window(year: int | None) -> tuple[int, ...]:
    current_year = year or date.today().year
    return tuple(range(current_year, current_year - 5, -1))


def _month_number(month_name: str) -> int:
    return {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }[month_name[:3].lower()]


def _is_kenai_relevant(record: dict[str, object]) -> bool:
    location = record.get("location")
    if not isinstance(location, str):
        return False
    normalized_location = location.lower()
    return any(term in normalized_location for term in KENAI_RELEVANT_TERMS)
