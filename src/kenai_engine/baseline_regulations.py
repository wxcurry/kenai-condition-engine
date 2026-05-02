"""Manual-review baseline regulation loading."""

from __future__ import annotations

import json
from pathlib import Path

from kenai_engine.models import BaselineRegulation

DEFAULT_BASELINE_REGULATIONS_PATH = Path("data/config/baseline_regulations.json")


def load_baseline_regulations(
    path: Path = DEFAULT_BASELINE_REGULATIONS_PATH,
) -> list[BaselineRegulation]:
    """Load structured baseline regulation context if the config file exists."""

    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload["baseline_regulations"] if isinstance(payload, dict) else payload
    return [BaselineRegulation.model_validate(record) for record in records]
