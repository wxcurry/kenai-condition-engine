"""ADF&G fishing reports source adapter."""

from __future__ import annotations

import re
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from kenai_engine.config import Settings
from kenai_engine.models import Alert
from kenai_engine.sources.usgs import RawSnapshot
from kenai_engine.utils.http import build_http_client
from kenai_engine.utils.time import utc_now

ADFG_FISHING_REPORTS_URL = "https://www.adfg.alaska.gov/sf/FishingReports/"
ADFG_BASE_URL = "https://www.adfg.alaska.gov/"
_KENAI_RELEVANCE_PATTERN = re.compile(r"\b(?:kenai|russian\s+river|soldotna|kasilof)\b", re.I)
_WHITESPACE_PATTERN = re.compile(r"\s+")


class AdfgFishingReportsAdapter:
    """ADF&G sport fishing reports adapter.

    Reports are official narrative context. They normalize to informational
    alerts and should not directly drive numeric scores without explicit rules.
    """

    source_name = "adfg_fishing_reports"

    def __init__(
        self,
        settings: Settings,
        client: httpx.Client | None = None,
        url: str = ADFG_FISHING_REPORTS_URL,
    ) -> None:
        self._settings = settings
        self._client = client
        self._url = url

    def fetch(self) -> RawSnapshot:
        client = self._client or build_http_client(self._settings)
        should_close = self._client is None
        try:
            response = client.get(self._url)
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


def parse_fishing_reports(html: str, base_url: str = ADFG_BASE_URL) -> list[Alert]:
    """Parse Kenai-relevant ADF&G fishing reports into informational alerts."""

    soup = BeautifulSoup(html, "lxml")
    alerts: list[Alert] = []
    seen_titles: set[str] = set()
    for container in soup.select("article, li, tr"):
        link = container.find("a", href=True)
        if link is None:
            continue
        title = _clean_text(link.get_text(" ", strip=True))
        href = str(link.get("href", ""))
        if not title or "report" not in title.lower() and "FishingReports" not in href:
            continue
        summary = _summary_from_container(container, title)
        searchable_text = _clean_text(f"{title} {summary}")
        title_is_relevant = bool(_KENAI_RELEVANCE_PATTERN.search(title))
        if "fishing report" in title.lower() and not title_is_relevant:
            continue
        if not _KENAI_RELEVANCE_PATTERN.search(searchable_text):
            continue
        if title in seen_titles:
            continue
        seen_titles.add(title)
        source_url = urljoin(base_url, href)
        alerts.append(
            Alert(
                title=title,
                severity="info",
                summary=_clean_text(f"{summary} Source: {source_url}") if summary else source_url,
                source="adfg_fishing_reports",
            )
        )
    return alerts


def _summary_from_container(container, title: str) -> str:
    text = _clean_text(container.get_text(" ", strip=True))
    if not text:
        return ""
    return _clean_text(text.replace(title, "", 1))


def _clean_text(text: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", text).strip()
