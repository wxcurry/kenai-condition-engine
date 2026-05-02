"""ADFG fish counts source adapter."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

from kenai_engine.config import Settings
from kenai_engine.sources.usgs import RawSnapshot
from kenai_engine.utils.http import build_http_client
from kenai_engine.utils.time import utc_now

ADFG_FISH_COUNTS_URL = "https://www.adfg.alaska.gov/sf/FishCounts/"


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


def parse_fish_counts(payload: str) -> list[dict[str, object]]:
    """Extract simple fish count records from JSON or HTML fixtures."""

    json_counts = _parse_json_counts(payload)
    if json_counts:
        return json_counts
    return _parse_html_table_counts(payload)


def _parse_json_counts(payload: str) -> list[dict[str, object]]:
    document = _load_json_document(payload)
    if document is None:
        return []

    rows: object
    if isinstance(document, list):
        rows = document
    elif isinstance(document, dict):
        rows = (
            document.get("fish_counts")
            or document.get("fishCounts")
            or document.get("counts")
            or document.get("data")
            or []
        )
    else:
        rows = []

    if not isinstance(rows, list):
        return []

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

    match = re.search(r"(\{.*\}|\[.*\])", payload, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _parse_html_table_counts(html: str) -> list[dict[str, object]]:
    soup = BeautifulSoup(html, "lxml")
    counts: list[dict[str, object]] = []

    for table in soup.select("table"):
        headers = [
            _canonical_header(cell.get_text(" ", strip=True))
            for cell in table.select("tr th")
        ]
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
    species = _string_value(row, "species")
    location = _string_value(row, "location")
    count = _count_value(row.get("count"))
    if not species or not location or count is None:
        return {}

    record: dict[str, object] = {
        "species": species,
        "location": location,
        "count": count,
    }
    observation_date = _string_value(row, "observation_date")
    source_url = _string_value(row, "source_url")
    if observation_date:
        record["observation_date"] = observation_date
    if source_url:
        record["source_url"] = source_url
    return record


def _canonical_header(header: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", header.lower()).strip("_")
    aliases = {
        "date": "observation_date",
        "observed": "observation_date",
        "observation_date": "observation_date",
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
