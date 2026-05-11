import json
from datetime import UTC, datetime

from kenai_engine.delivery import prepare_public_report
from kenai_engine.report_builder import build_condition_report


def test_prepare_public_report_writes_versioned_latest_json(tmp_path) -> None:
    report = build_condition_report(datetime(2026, 5, 2, 12, 0, tzinfo=UTC))

    path = prepare_public_report(report, tmp_path / "public")

    assert path == tmp_path / "public" / "v1" / "latest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0.0"
    assert payload["generated_by"] == "kenai-condition-engine"
