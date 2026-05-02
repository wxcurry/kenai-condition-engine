"""Static app-delivery helpers."""

from __future__ import annotations

import json
from pathlib import Path

from kenai_engine.models import Report


def prepare_public_report(report: Report, public_dir: Path) -> Path:
    """Write the versioned static JSON consumed by Android/dev clients."""

    output_dir = public_dir / "v1"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "latest.json"
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path
