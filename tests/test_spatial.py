import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from kenai_engine.spatial import load_spatial_catalog, resolve_spot


def test_spatial_catalog_loads_default_access_points() -> None:
    catalog = load_spatial_catalog()

    assert catalog.schema_version == "1.0.0"
    assert {spot.id for spot in catalog.access_points} >= {
        "cooper_landing_upper_kenai",
        "soldotna",
        "kenai_river_mouth",
    }


def test_resolve_spot_returns_stable_source_relevance() -> None:
    spot = resolve_spot("soldotna")

    assert spot.name == "Soldotna"
    assert spot.segment == "soldotna"
    assert any(
        relevance.source == "usgs" and relevance.source_id == "15266300"
        for relevance in spot.source_relevance
    )


def test_invalid_spatial_catalog_fails_clearly(tmp_path: Path) -> None:
    invalid_path = tmp_path / "spatial_catalog.json"
    invalid_path.write_text(json.dumps({"schema_version": "1.0.0"}), encoding="utf-8")

    with pytest.raises(ValidationError):
        load_spatial_catalog(invalid_path)
