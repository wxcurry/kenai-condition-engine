from datetime import UTC, datetime

from kenai_engine.report_builder import build_placeholder_report, write_latest_report


def test_placeholder_report_has_app_contract_shape() -> None:
    report = build_placeholder_report(datetime(2026, 5, 2, 12, 0, tzinfo=UTC))

    dumped = report.model_dump(mode="json")

    assert set(dumped) == {
        "report_date",
        "generated_at",
        "river",
        "overall_score",
        "overall_status",
        "confidence",
        "summary",
        "locations",
        "regulations",
        "fish_counts",
        "alerts",
        "source_health",
    }
    assert dumped["river"] == "Kenai River"
    assert dumped["source_health"]


def test_write_latest_report_creates_json_file(tmp_path) -> None:
    path = write_latest_report(tmp_path)

    assert path.name == "latest.json"
    assert path.exists()
