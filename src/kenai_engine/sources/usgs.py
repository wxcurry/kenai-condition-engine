"""USGS source adapter placeholder."""

from __future__ import annotations

from pydantic import BaseModel

from kenai_engine.config import Settings
from kenai_engine.utils.time import utc_now


class RawSnapshot(BaseModel):
    """Raw source payload captured by an adapter."""

    source: str
    fetched_at: str
    payload: str


class UsgsAdapter:
    """Placeholder USGS adapter."""

    source_name = "usgs"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def fetch(self) -> RawSnapshot:
        site_ids = ",".join(self._settings.usgs_site_ids)
        return RawSnapshot(
            source=self.source_name,
            fetched_at=utc_now().isoformat(),
            payload=f'{{"placeholder": true, "site_ids": "{site_ids}"}}',
        )


def parse_usgs_payload(payload: str) -> dict[str, object]:
    """Parse a placeholder USGS payload into a normalized dictionary."""

    return {"source": "usgs", "raw": payload, "implemented": False}
