"""ADFG emergency orders source adapter."""

from __future__ import annotations

import re
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag

from kenai_engine.config import Settings
from kenai_engine.sources.usgs import RawSnapshot
from kenai_engine.utils.http import build_http_client
from kenai_engine.utils.time import utc_now

ADFG_BASE_URL = "https://www.adfg.alaska.gov/"
ADFG_EMERGENCY_ORDERS_URL = "https://www.adfg.alaska.gov/sf/EONR/"

_ORDER_TITLE_PATTERN = re.compile(r"\b(?:emergency\s+order|e\.?o\.?)\b", re.IGNORECASE)
_WHITESPACE_PATTERN = re.compile(r"\s+")


class AdfgEmergencyOrdersAdapter:
    """ADFG emergency orders adapter."""

    source_name = "adfg_emergency_orders"

    def __init__(
        self,
        settings: Settings,
        client: httpx.Client | None = None,
        url: str = ADFG_EMERGENCY_ORDERS_URL,
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


def parse_emergency_orders(html: str, base_url: str = ADFG_BASE_URL) -> list[dict[str, str]]:
    """Extract simple emergency-order links from HTML.

    This is intentionally small and fixture-driven until the real ADFG page
    contract is chosen.
    """

    soup = BeautifulSoup(html, "lxml")
    orders: list[dict[str, str]] = []
    for link in soup.select("a"):
        title = link.get_text(" ", strip=True)
        href = link.get("href")
        if not title or not isinstance(href, str) or not _looks_like_order(title, href):
            continue

        order = {
            "title": _clean_text(title),
            "url": urljoin(base_url, href),
        }
        summary = _extract_summary(link, title)
        if summary:
            order["summary"] = summary
        status = _detect_status(f"{title} {summary}")
        if status:
            order["status"] = status

        orders.append(order)
    return orders


def _looks_like_order(title: str, href: str) -> bool:
    return bool(_ORDER_TITLE_PATTERN.search(title)) or "emergency" in href.lower()


def _extract_summary(link: Tag, title: str) -> str:
    container = link.find_parent("tr")
    if container is None:
        container = link.find_parent(["article", "section", "li", "div"])
    if container is None:
        return ""

    text = _clean_text(container.get_text(" ", strip=True))
    summary = text.replace(_clean_text(title), "", 1)
    return _clean_text(summary)


def _detect_status(text: str) -> str:
    normalized = text.lower()
    if any(keyword in normalized for keyword in ("closed", "closure", "closes")):
        return "closure"
    if any(keyword in normalized for keyword in ("restrict", "restriction", "restricted")):
        return "restriction"
    return ""


def _clean_text(text: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", text).strip()
