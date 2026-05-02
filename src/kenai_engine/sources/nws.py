"""National Weather Service adapter placeholder."""

from __future__ import annotations

from kenai_engine.config import Settings
from kenai_engine.sources.usgs import RawSnapshot
from kenai_engine.utils.time import utc_now


class NwsAdapter:
    """Placeholder NWS adapter."""

    source_name = "nws"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def fetch(self) -> RawSnapshot:
        locations = ",".join(self._settings.nws_locations)
        return RawSnapshot(
            source=self.source_name,
            fetched_at=utc_now().isoformat(),
            payload=f'{{"placeholder": true, "locations": "{locations}"}}',
        )
