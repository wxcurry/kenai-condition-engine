"""ADFG emergency orders adapter placeholder."""

from __future__ import annotations

from bs4 import BeautifulSoup

from kenai_engine.config import Settings
from kenai_engine.sources.usgs import RawSnapshot
from kenai_engine.utils.time import utc_now


class AdfgEmergencyOrdersAdapter:
    """Placeholder ADFG emergency orders adapter."""

    source_name = "adfg_emergency_orders"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def fetch(self) -> RawSnapshot:
        return RawSnapshot(
            source=self.source_name,
            fetched_at=utc_now().isoformat(),
            payload='{"placeholder": true, "active_orders": []}',
        )


def parse_emergency_orders(html: str) -> list[dict[str, str]]:
    """Extract simple emergency-order links from HTML.

    This is intentionally small and fixture-driven until the real ADFG page
    contract is chosen.
    """

    soup = BeautifulSoup(html, "lxml")
    orders: list[dict[str, str]] = []
    for link in soup.select("a"):
        title = link.get_text(" ", strip=True)
        href = link.get("href")
        if title and href and "emergency" in title.lower():
            orders.append({"title": title, "url": href})
    return orders
