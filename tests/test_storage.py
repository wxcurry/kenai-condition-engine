import sqlite3
from pathlib import Path

from kenai_engine.condition_variables import (
    CONDITION_VARIABLES,
    KENAI_RIVER_VARIABLE_NAMES,
    REQUESTED_TP_VARIABLE_NAMES,
)
from kenai_engine.db import initialize_database
from kenai_engine.storage import raw_snapshots
from kenai_engine.storage.normalized_records import save_normalized_record
from kenai_engine.storage.raw_snapshots import save_raw_snapshot


def test_initialize_database_creates_storage_constraints_and_indexes() -> None:
    connection = _connection()

    initialize_database(connection)
    initialize_database(connection)

    raw_columns = _table_columns(connection, "raw_snapshots")
    normalized_columns = _table_columns(connection, "normalized_records")
    indexes = _indexes(connection)

    assert raw_columns == {
        "id": {"notnull": False, "pk": True},
        "source": {"notnull": True, "pk": False},
        "fetched_at": {"notnull": True, "pk": False},
        "payload": {"notnull": True, "pk": False},
    }
    assert normalized_columns == {
        "id": {"notnull": False, "pk": True},
        "record_type": {"notnull": True, "pk": False},
        "observed_at": {"notnull": True, "pk": False},
        "payload": {"notnull": True, "pk": False},
    }
    assert "idx_raw_snapshots_source_fetched_at_id" in indexes
    assert "idx_normalized_records_type_observed_at_id" in indexes
    assert indexes["ux_normalized_records_type_observed_payload"]["unique"]


def test_initialize_database_creates_condition_variable_metadata() -> None:
    connection = _connection()

    initialize_database(connection)

    columns = _table_columns(connection, "condition_variables")
    indexes = _indexes(connection)

    assert columns == {
        "name": {"notnull": True, "pk": True},
        "description": {"notnull": True, "pk": False},
        "data_type": {"notnull": True, "pk": False},
        "unit": {"notnull": True, "pk": False},
        "valid_range": {"notnull": True, "pk": False},
        "default_value": {"notnull": True, "pk": False},
        "source_url": {"notnull": True, "pk": False},
        "source_title": {"notnull": True, "pk": False},
        "source_organization": {"notnull": True, "pk": False},
        "date_accessed": {"notnull": True, "pk": False},
        "code_locations": {"notnull": True, "pk": False},
        "calculation_notes": {"notnull": True, "pk": False},
        "status": {"notnull": True, "pk": False},
        "display_name": {"notnull": True, "pk": False},
        "category": {"notnull": True, "pk": False},
        "kenai_relevance": {"notnull": True, "pk": False},
        "collection_method": {"notnull": True, "pk": False},
        "calculation_method": {"notnull": True, "pk": False},
        "proxy_method": {"notnull": True, "pk": False},
        "update_frequency": {"notnull": True, "pk": False},
        "limitations": {"notnull": True, "pk": False},
    }
    assert "ux_condition_variables_name" in indexes
    assert indexes["ux_condition_variables_name"]["unique"]


def test_initialize_database_seeds_requested_tp_variables_once() -> None:
    connection = _connection()

    initialize_database(connection)
    initialize_database(connection)

    rows = connection.execute(
        """
        SELECT name, source_url
        FROM condition_variables
        WHERE name IN ({})
        ORDER BY name
        """.format(",".join("?" for _ in REQUESTED_TP_VARIABLE_NAMES)),
        tuple(REQUESTED_TP_VARIABLE_NAMES),
    ).fetchall()

    assert [row["name"] for row in rows] == sorted(REQUESTED_TP_VARIABLE_NAMES)
    assert all(row["source_url"].startswith("https://") for row in rows)
    assert (
        connection.execute("SELECT COUNT(*) FROM condition_variables").fetchone()[0]
        == connection.execute("SELECT COUNT(DISTINCT name) FROM condition_variables").fetchone()[0]
    )


def test_initialize_database_seeds_kenai_river_variables_with_rich_metadata() -> None:
    connection = _connection()

    initialize_database(connection)
    initialize_database(connection)

    rows = connection.execute(
        """
        SELECT
            name,
            display_name,
            category,
            kenai_relevance,
            source_url,
            collection_method,
            calculation_method,
            proxy_method,
            limitations
        FROM condition_variables
        WHERE name IN ({})
        ORDER BY name
        """.format(",".join("?" for _ in KENAI_RIVER_VARIABLE_NAMES)),
        tuple(KENAI_RIVER_VARIABLE_NAMES),
    ).fetchall()

    assert [row["name"] for row in rows] == sorted(KENAI_RIVER_VARIABLE_NAMES)
    assert all(row["display_name"] for row in rows)
    assert all(row["category"] for row in rows)
    assert all("Kenai" in row["kenai_relevance"] for row in rows)
    assert all(
        row["source_url"].startswith("https://") or row["source_url"] == "source_needed"
        for row in rows
    )
    assert all(row["collection_method"] for row in rows)
    assert all(row["calculation_method"] for row in rows)
    assert all(row["limitations"] for row in rows)


def test_initialize_database_upgrades_legacy_condition_variable_table() -> None:
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE condition_variables (
            name TEXT PRIMARY KEY NOT NULL,
            description TEXT NOT NULL,
            data_type TEXT NOT NULL,
            unit TEXT NOT NULL,
            valid_range TEXT NOT NULL,
            default_value TEXT NOT NULL,
            source_url TEXT NOT NULL,
            source_title TEXT NOT NULL,
            source_organization TEXT NOT NULL,
            date_accessed TEXT NOT NULL,
            code_locations TEXT NOT NULL,
            calculation_notes TEXT NOT NULL,
            status TEXT NOT NULL
        );
        """
    )

    initialize_database(connection)

    column_names = [
        row[1] for row in connection.execute("PRAGMA table_info(condition_variables)").fetchall()
    ]
    row = connection.execute(
        """
        SELECT display_name, category, kenai_relevance
        FROM condition_variables
        WHERE name = 'hours_after_hot_sunny_day'
        """
    ).fetchone()

    assert "display_name" in column_names
    assert "limitations" in column_names
    assert row == (
        "Hours After Hot Sunny Day",
        "weather",
        (
            "Kenai River fishing conditions can change after warm sunny periods that may raise "
            "shallow near-bank water temperatures and alter angler/fish timing."
        ),
    )


def test_kenai_river_variable_reference_file_includes_all_requested_variables() -> None:
    reference = Path("docs/KENAI_RIVER_VARIABLE_REFERENCES.md").read_text(encoding="utf-8")

    assert "# Kenai River Condition Calculation Variable References" in reference
    for variable_name in KENAI_RIVER_VARIABLE_NAMES:
        assert f"`{variable_name}`" in reference


def test_variable_reference_file_includes_all_seeded_condition_variables() -> None:
    reference = Path("docs/VARIABLE_REFERENCES.md").read_text(encoding="utf-8")

    for variable in CONDITION_VARIABLES:
        assert f"`{variable.name}`" in reference


def test_save_normalized_record_is_idempotent_for_duplicate_record() -> None:
    connection = _connection()
    initialize_database(connection)

    first_id = save_normalized_record(
        connection,
        record_type="flow",
        observed_at="2026-05-02T12:00:00+00:00",
        payload='{"cfs": 8150}',
    )
    second_id = save_normalized_record(
        connection,
        record_type="flow",
        observed_at="2026-05-02T12:00:00+00:00",
        payload='{"cfs": 8150}',
    )

    row_count = connection.execute("SELECT COUNT(*) FROM normalized_records").fetchone()[0]

    assert second_id == first_id
    assert row_count == 1


def test_save_normalized_record_allows_same_time_with_different_payload() -> None:
    connection = _connection()
    initialize_database(connection)

    first_id = save_normalized_record(
        connection,
        record_type="flow",
        observed_at="2026-05-02T12:00:00+00:00",
        payload='{"cfs": 8150}',
    )
    second_id = save_normalized_record(
        connection,
        record_type="flow",
        observed_at="2026-05-02T12:00:00+00:00",
        payload='{"cfs": 8200}',
    )

    row_count = connection.execute("SELECT COUNT(*) FROM normalized_records").fetchone()[0]

    assert second_id != first_id
    assert row_count == 2


def test_list_latest_raw_snapshots_returns_newest_snapshot_per_source() -> None:
    connection = _connection()
    initialize_database(connection)
    save_raw_snapshot(
        connection,
        source="usgs",
        fetched_at="2026-05-02T12:00:00+00:00",
        payload="older usgs",
    )
    latest_nws_id = save_raw_snapshot(
        connection,
        source="nws",
        fetched_at="2026-05-02T12:04:00+00:00",
        payload="latest nws",
    )
    latest_usgs_id = save_raw_snapshot(
        connection,
        source="usgs",
        fetched_at="2026-05-02T12:05:00+00:00",
        payload="latest usgs",
    )
    latest_fish_counts_id = save_raw_snapshot(
        connection,
        source="adfg_fish_counts",
        fetched_at="2026-05-02T12:01:00+00:00",
        payload="older adfg",
    )

    rows = raw_snapshots.list_latest_raw_snapshots(connection)

    assert [row["id"] for row in rows] == [latest_usgs_id, latest_nws_id, latest_fish_counts_id]
    assert [row["source"] for row in rows] == ["usgs", "nws", "adfg_fish_counts"]
    assert rows[0]["payload"] == "latest usgs"
    assert rows[1]["payload"] == "latest nws"
    assert rows[2]["payload"] == "older adfg"


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    return connection


def _table_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> dict[str, dict[str, bool]]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {
        row["name"]: {"notnull": bool(row["notnull"]), "pk": bool(row["pk"])}
        for row in rows
    }


def _indexes(connection: sqlite3.Connection) -> dict[str, dict[str, bool]]:
    rows = connection.execute(
        """
        SELECT name, [unique]
        FROM pragma_index_list('raw_snapshots')
        UNION ALL
        SELECT name, [unique]
        FROM pragma_index_list('normalized_records')
        UNION ALL
        SELECT name, [unique]
        FROM pragma_index_list('condition_variables')
        """
    ).fetchall()
    return {row["name"]: {"unique": bool(row["unique"])} for row in rows}
