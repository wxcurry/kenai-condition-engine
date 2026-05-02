from datetime import UTC, datetime

from kenai_engine.models import Regulation
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


def test_explicit_empty_inputs_do_not_insert_placeholder_records() -> None:
    report = build_placeholder_report(
        datetime(2026, 5, 2, 12, 0, tzinfo=UTC),
        regulations=[],
        fish_counts=[],
        alerts=[],
    )

    assert report.regulations == []
    assert report.fish_counts == []
    assert report.alerts == []
    assert _source_health_message(report, "adfg_emergency_orders") == (
        "0 normalized ADFG emergency orders available."
    )
    assert _source_health_message(report, "adfg_fish_counts") == (
        "0 normalized ADFG fish count records available."
    )
    assert _source_health_message(report, "nws") == "0 normalized NWS alerts available."


def test_real_closed_regulation_overrides_placeholder_status() -> None:
    report = build_placeholder_report(
        datetime(2026, 5, 2, 12, 0, tzinfo=UTC),
        regulations=[
            Regulation(
                title="Kenai River closure",
                status="closed",
                effective_date=datetime(2026, 5, 2, tzinfo=UTC).date(),
                source_url="https://www.adfg.alaska.gov/",
                summary="Emergency order closes the fishery.",
            )
        ],
        fish_counts=[],
        alerts=[],
    )

    assert report.overall_status == "closed"
    assert report.overall_score == 0
    assert report.summary == (
        "Active emergency order indicates a closure. Check official ADFG sources."
    )


def test_real_restricted_regulation_overrides_placeholder_status() -> None:
    report = build_placeholder_report(
        datetime(2026, 5, 2, 12, 0, tzinfo=UTC),
        regulations=[
            Regulation(
                title="Kenai River restriction",
                status="restricted",
                effective_date=datetime(2026, 5, 2, tzinfo=UTC).date(),
                source_url="https://www.adfg.alaska.gov/",
                summary="Emergency order restricts the fishery.",
            )
        ],
        fish_counts=[],
        alerts=[],
    )

    assert report.overall_status == "restricted"
    assert report.overall_score == 45
    assert report.summary == (
        "Active emergency order indicates restrictions. Check official ADFG sources."
    )


def _source_health_message(report, source: str) -> str:
    return next(health.message for health in report.source_health if health.source == source)
