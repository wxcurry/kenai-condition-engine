"""Spatial catalog helpers for prototype predictions."""

from __future__ import annotations

import json
from pathlib import Path

from kenai_engine.models import AccessPoint, SpatialCatalog

DEFAULT_SPATIAL_CATALOG_PATH = Path("data/config/spatial_catalog.json")


def load_spatial_catalog(path: Path = DEFAULT_SPATIAL_CATALOG_PATH) -> SpatialCatalog:
    """Load and validate the spatial catalog."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    return SpatialCatalog.model_validate(payload)


def resolve_spot(spot_id: str, catalog: SpatialCatalog | None = None) -> AccessPoint:
    """Return an access point by stable ID."""

    active_catalog = catalog or load_spatial_catalog()
    for spot in active_catalog.access_points:
        if spot.id == spot_id:
            return spot
    raise KeyError(f"Unknown spot_id: {spot_id}")


def list_spot_ids(catalog: SpatialCatalog | None = None) -> list[str]:
    """Return stable access point IDs in catalog order."""

    active_catalog = catalog or load_spatial_catalog()
    return [spot.id for spot in active_catalog.access_points]
