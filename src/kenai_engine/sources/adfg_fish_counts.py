"""ADFG fish counts source adapter."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup

from kenai_engine.config import Settings
from kenai_engine.sources.usgs import RawSnapshot
from kenai_engine.utils.http import build_http_client
from kenai_engine.utils.time import utc_now

ADFG_FISH_COUNTS_URL = "https://www.adfg.alaska.gov/sf/FishCounts/"
KENAI_RELEVANT_TERMS = ("kenai", "russian", "kasilof")


class AdfgFishCountsAdapter:
    """ADFG fish counts adapter."""

    source_name = "adfg_fish_counts"

    def __init__(
        self,
        settings: Settings,
        *,
        source_url: str = ADFG_FISH_COUNTS_URL,
        client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings
        self._source_url = source_url
        self._client = client

    def fetch(self) -> RawSnapshot:
        client = self._client or build_http_client(self._settings)
        should_close = self._client is None
        try:
            response = client.get(self._source_url)
            response.raise_for_status()
            payload = response.text
        finally:
            if should_close:
                client.close()

        return RawSnapshot(
            source=self.source_name,
            fetched_at=utc_now().isoformat(),
            payload=payload,
        )


def parse_fish_counts(payload: str, *, relevant_only: bool = True) -> list[dict[str, object]]:
    """Extract simple fish count records from JSON or HTML fixtures."""

    json_counts = _parse_json_counts(payload)
    counts = json_counts if json_counts else _parse_html_table_counts(payload)
    if relevant_only:
        return [record for record in counts if _is_kenai_relevant(record)]
    return counts


def _parse_json_counts(payload: str) -> list[dict[str, object]]:
    document = _load_json_document(payload)
    if document is None:
        return []

    rows = _extract_json_rows(document)

    counts: list[dict[str, object]] = []
    for row in rows:
        if isinstance(row, dict):
            record = _normalize_record(row)
            if record:
                counts.append(record)
    return counts


def _load_json_document(payload: str) -> object | None:
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for match in re.finditer(r"[\[{]", payload):
        try:
            document, _ = decoder.raw_decode(payload[match.start() :])
        except json.JSONDecodeError:
            continue
        if _extract_json_rows(document):
            return document
    return None


def _extract_json_rows(document: object) -> list[object]:
    if isinstance(document, list):
        return document
    if not isinstance(document, dict):
        return []

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


def _normalize_record(row: dict[str, Any]) -> dict[str, object]:
    normalized_row = _canonicalize_row(row)
    species = _string_value(normalized_row, "species")
    location = _string_value(normalized_row, "location")
    count = _count_value(normalized_row.get("count"))
    observation_date = _date_value(normalized_row.get("observation_date"))
    if not species or not location or count is None or observation_date is None:
        return {}

    record: dict[str, object] = {
        "species": species,
        "location": location,
        "count": count,
        "observation_date": observation_date,
    }
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
        "site": "location",
        "passage": "count",
        "cumulative": "count",
        "source": "source_url",
        "source_url": "source_url",
        "url": "source_url",
    }
    if normalized in {"species", "location", "count"}:
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

    for date_format in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text, date_format).date().isoformat()
        except ValueError:
            continue
    return None


def _is_kenai_relevant(record: dict[str, object]) -> bool:
    location = record.get("location")
    if not isinstance(location, str):
        return False
    normalized_location = location.lower()
    return any(term in normalized_location for term in KENAI_RELEVANT_TERMS)
