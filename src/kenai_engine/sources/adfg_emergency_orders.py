"""ADFG emergency orders source adapter."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from urllib.parse import urljoin, urlparse

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
_KENAI_RELEVANCE_PATTERN = re.compile(
    r"\b(?:kenai|kasilof|russian\s+river|2-(?:ks|rs)-)\b",
    re.IGNORECASE,
)
_MONTH_DATE_PATTERN = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"\d{1,2},\s+\d{4}\b",
    re.IGNORECASE,
)


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
            detail_payloads = _fetch_detail_payloads(client, self._url, payload)
            if detail_payloads:
                payload = _bundle_payload(payload, detail_payloads)
        finally:
            if should_close:
                client.close()

        return RawSnapshot(
            source=self.source_name,
            fetched_at=utc_now().isoformat(),
            payload=payload,
        )


def parse_emergency_orders(
    html: str,
    base_url: str = ADFG_BASE_URL,
    is_relevant: Callable[[str], bool] | None = None,
) -> list[dict[str, str]]:
    """Extract simple emergency-order links from HTML.

    This is intentionally small and fixture-driven until the real ADFG page
    contract is chosen.
    """

    soup = BeautifulSoup(html, "lxml")
    orders: list[dict[str, str]] = []
    seen_keys: set[tuple[str, str]] = set()
    relevance_predicate = is_relevant or _is_kenai_relevant
    for detail in _detail_documents(soup, base_url):
        detail_text = _clean_text(f"{detail.get('title', '')} {detail.get('summary', '')}")
        if not detail_text or not relevance_predicate(detail_text):
            continue
        key = (detail.get("title", ""), detail.get("url", ""))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        orders.append(detail)

    for link in soup.select("a"):
        title = link.get_text(" ", strip=True)
        href = link.get("href")
        if not title or not isinstance(href, str) or not _looks_like_order(title, href):
            continue

        summary = _extract_summary(link, title)
        searchable_text = _clean_text(f"{title} {summary}")
        if not relevance_predicate(searchable_text):
            continue

        order = {
            "title": _clean_text(title),
            "url": urljoin(base_url, href),
        }
        if summary:
            order["summary"] = summary
        status = _detect_status(searchable_text)
        if status:
            order["status"] = status
        if _is_pdf_url(order["url"]):
            order["manual_review_required"] = "true"
            order["content_type"] = "pdf"
        order.update(_extract_dates(searchable_text))

        key = (order.get("title", ""), order.get("url", ""))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        orders.append(order)
    return orders


def parse_emergency_order_detail(html: str, source_url: str) -> dict[str, str]:
    """Extract a normalized emergency order from an ADF&G detail document."""

    soup = BeautifulSoup(html, "lxml")
    container = soup.select_one("main, article, .node-news-release, body")
    if container is None:
        return {}

    heading = container.find(["h1", "h2", "h3"])
    title = _clean_text(heading.get_text(" ", strip=True) if heading else "")
    if not title or not _looks_like_order(title, source_url):
        return {}

    paragraphs = [
        _clean_text(element.get_text(" ", strip=True))
        for element in container.find_all(["p", "div"], recursive=True)
        if _clean_text(element.get_text(" ", strip=True))
    ]
    summary_parts = [text for text in paragraphs if text != title]
    summary = _dedupe_summary_text(" ".join(summary_parts))
    searchable_text = _clean_text(f"{title} {summary}")

    order = {
        "title": title,
        "url": source_url,
    }
    if summary:
        order["summary"] = summary
    status = _detect_status(searchable_text)
    if status:
        order["status"] = status
    order.update(_extract_dates(searchable_text))
    return order


def _fetch_detail_payloads(
    client: httpx.Client,
    list_url: str,
    list_payload: str,
) -> list[tuple[str, str]]:
    detail_payloads: list[tuple[str, str]] = []
    seen_urls: set[str] = set()
    for order in parse_emergency_orders(list_payload, base_url=list_url):
        detail_url = order.get("url", "")
        if not _should_fetch_detail(list_url, detail_url) or detail_url in seen_urls:
            continue
        seen_urls.add(detail_url)
        response = client.get(detail_url)
        response.raise_for_status()
        detail_payloads.append((detail_url, response.text))
    return detail_payloads


def _bundle_payload(list_payload: str, detail_payloads: list[tuple[str, str]]) -> str:
    detail_documents = "\n".join(
        f'<article data-source-url="{url}">\n{detail_html}\n</article>'
        for url, detail_html in detail_payloads
    )
    return f"{list_payload}\n<section data-adfg-detail-documents>\n{detail_documents}\n</section>"


def _detail_documents(soup: BeautifulSoup, base_url: str) -> list[dict[str, str]]:
    details: list[dict[str, str]] = []
    for detail_container in soup.select("[data-source-url]"):
        source_url = detail_container.get("data-source-url")
        if not isinstance(source_url, str):
            continue
        detail = parse_emergency_order_detail(
            str(detail_container),
            source_url=urljoin(base_url, source_url),
        )
        if detail:
            details.append(detail)
    return details


def _should_fetch_detail(list_url: str, detail_url: str) -> bool:
    if not detail_url or _is_pdf_url(detail_url):
        return False
    list_host = urlparse(list_url).netloc
    detail_host = urlparse(detail_url).netloc
    return not detail_host or detail_host == list_host


def _is_pdf_url(url: str) -> bool:
    return url.lower().split("?", 1)[0].endswith(".pdf")


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
    if any(keyword in normalized for keyword in ("open", "opens", "reopen")):
        return "open"
    return ""


def _extract_dates(text: str) -> dict[str, str]:
    dates: dict[str, str] = {}
    effective = _extract_labeled_date(text, ("effective", "beginning"))
    if effective:
        dates["effective_date"] = effective
    expires = _extract_labeled_date(text, ("through", "until", "expires"))
    if expires:
        dates["expires_date"] = expires
    return dates


def _extract_labeled_date(text: str, labels: tuple[str, ...]) -> str:
    for label in labels:
        match = re.search(
            rf"\b{label}\b(?P<date_text>.*?{_MONTH_DATE_PATTERN.pattern})",
            text,
            re.IGNORECASE,
        )
        if match:
            date_match = _MONTH_DATE_PATTERN.search(match.group("date_text"))
            if date_match:
                return _to_iso_date(date_match.group(0))
    return ""


def _to_iso_date(date_text: str) -> str:
    try:
        return datetime.strptime(date_text, "%B %d, %Y").date().isoformat()
    except ValueError:
        return ""


def _is_kenai_relevant(text: str) -> bool:
    return bool(_KENAI_RELEVANCE_PATTERN.search(text))


def _clean_text(text: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", text).strip()


def _dedupe_summary_text(text: str) -> str:
    parts = _clean_text(text).split(" ")
    midpoint = len(parts) // 2
    if len(parts) >= 8 and len(parts) % 2 == 0 and parts[:midpoint] == parts[midpoint:]:
        return " ".join(parts[:midpoint])
    return _clean_text(text)
