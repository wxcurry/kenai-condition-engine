"""USGS instantaneous-values source adapter."""

from __future__ import annotations

import json

import httpx
from pydantic import BaseModel

from kenai_engine.config import Settings
from kenai_engine.models import UsgsObservation
from kenai_engine.utils.http import build_http_client
from kenai_engine.utils.time import utc_now

USGS_IV_URL = "https://waterservices.usgs.gov/nwis/iv/"
USGS_PARAMETER_CODES = ("00060", "00065", "00010")


class RawSnapshot(BaseModel):
    """Raw source payload captured by an adapter."""

    source: str
    fetched_at: str
    payload: str


class UsgsAdapter:
    """USGS instantaneous-values adapter."""

    source_name = "usgs"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = client

    def fetch(self) -> RawSnapshot:
        client = self._client or build_http_client(self._settings)
        should_close = self._client is None
        try:
            response = client.get(
                USGS_IV_URL,
                params={
                    "format": "json",
                    "sites": ",".join(self._settings.usgs_site_ids),
                    "parameterCd": ",".join(USGS_PARAMETER_CODES),
                    "siteStatus": "active",
                },
            )
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


def parse_usgs_payload(payload: str) -> list[UsgsObservation]:
    """Parse USGS WaterML JSON into normalized observations."""

    document = json.loads(payload)
    observations: list[UsgsObservation] = []

    for series in document.get("value", {}).get("timeSeries", []):
        source_info = series.get("sourceInfo", {})
        variable = series.get("variable", {})
        site_id = _first_value(source_info.get("siteCode"))
        parameter_code = _first_value(variable.get("variableCode"))
        site_name = source_info.get("siteName", "")
        parameter_name = variable.get("variableName", "")
        unit = variable.get("unit", {}).get("unitCode", "")

        for values_group in series.get("values", []):
            for reading in values_group.get("value", []):
                raw_value = reading.get("value")
                observed_at = reading.get("dateTime")
                if site_id and parameter_code and raw_value is not None and observed_at:
                    observations.append(
                        UsgsObservation(
                            site_id=site_id,
                            site_name=site_name,
                            parameter_code=parameter_code,
                            parameter_name=parameter_name,
                            value=float(raw_value),
                            unit=unit,
                            observed_at=observed_at,
                            qualifiers=reading.get("qualifiers", []),
                        )
                    )

    return observations


def _first_value(items: object) -> str:
    if not isinstance(items, list) or not items:
        return ""
    first = items[0]
    if not isinstance(first, dict):
        return ""
    value = first.get("value")
    return value if isinstance(value, str) else ""
