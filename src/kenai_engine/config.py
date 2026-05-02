"""Environment-backed configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _csv_env(name: str, default: str) -> list[str]:
    raw_value = os.getenv(name, default)
    return [value.strip() for value in raw_value.split(",") if value.strip()]


def _semicolon_env(name: str, default: str) -> list[str]:
    raw_value = os.getenv(name, default)
    return [value.strip() for value in raw_value.split(";") if value.strip()]


@dataclass(frozen=True)
class Settings:
    """Runtime settings for the engine."""

    user_agent: str
    db_path: Path
    output_dir: Path
    raw_dir: Path
    usgs_site_ids: list[str]
    nws_locations: list[str]
    fetch_timeout_seconds: float
    noaa_tide_station_id: str = "9455742"
    public_dir: Path = Path("data/public")

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            user_agent=os.getenv(
                "KENAI_ENGINE_USER_AGENT",
                "kenai-condition-engine/0.1 (+https://example.invalid)",
            ),
            db_path=Path(os.getenv("KENAI_ENGINE_DB_PATH", "data/kenai_engine.sqlite3")),
            output_dir=Path(os.getenv("KENAI_ENGINE_OUTPUT_DIR", "data/reports")),
            public_dir=Path(os.getenv("KENAI_ENGINE_PUBLIC_DIR", "data/public")),
            raw_dir=Path(os.getenv("KENAI_ENGINE_RAW_DIR", "data/raw")),
            usgs_site_ids=_csv_env("USGS_SITE_IDS", "15258000,15266010,15266110,15266300"),
            nws_locations=_semicolon_env("NWS_LOCATIONS", "Kenai,AK"),
            fetch_timeout_seconds=float(os.getenv("FETCH_TIMEOUT_SECONDS", "20")),
            noaa_tide_station_id=os.getenv("NOAA_TIDE_STATION_ID", "9455742"),
        )
