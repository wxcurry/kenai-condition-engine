from pathlib import Path

from kenai_engine.sources.adfg_fishing_reports import parse_fishing_reports


def test_parse_fishing_reports_extracts_kenai_reports_as_information_alerts() -> None:
    alerts = parse_fishing_reports(_fixture("adfg_fishing_reports.html"))

    assert len(alerts) == 1
    assert alerts[0].title == "Northern Kenai Fishing Report"
    assert alerts[0].severity == "info"
    assert alerts[0].source == "adfg_fishing_reports"
    assert "Kenai River sockeye fishing has improved" in alerts[0].summary


def _fixture(name: str) -> str:
    return (Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8")
