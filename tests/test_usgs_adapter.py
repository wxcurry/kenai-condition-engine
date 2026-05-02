from kenai_engine.config import Settings
from kenai_engine.sources.usgs import UsgsAdapter, parse_usgs_payload


def test_usgs_adapter_returns_placeholder_snapshot(tmp_path) -> None:
    settings = Settings(
        user_agent="test-agent",
        db_path=tmp_path / "db.sqlite3",
        output_dir=tmp_path / "reports",
        raw_dir=tmp_path / "raw",
        usgs_site_ids=["15266300"],
        nws_locations=["Kenai,AK"],
        fetch_timeout_seconds=1,
    )

    snapshot = UsgsAdapter(settings).fetch()

    assert snapshot.source == "usgs"
    assert "15266300" in snapshot.payload


def test_parse_usgs_payload_marks_parser_as_stub() -> None:
    parsed = parse_usgs_payload('{"placeholder": true}')

    assert parsed["source"] == "usgs"
    assert parsed["implemented"] is False
