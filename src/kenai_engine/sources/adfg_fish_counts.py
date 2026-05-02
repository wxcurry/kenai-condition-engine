"""ADFG fish counts adapter placeholder."""

from __future__ import annotations

from kenai_engine.config import Settings
from kenai_engine.sources.usgs import RawSnapshot
from kenai_engine.utils.time import utc_now


class AdfgFishCountsAdapter:
    """Placeholder ADFG fish counts adapter."""

    source_name = "adfg_fish_counts"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def fetch(self) -> RawSnapshot:
        return RawSnapshot(
            source=self.source_name,
            fetched_at=utc_now().isoformat(),
            payload='{"placeholder": true, "fish_counts": []}',
        )
