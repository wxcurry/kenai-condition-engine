import sqlite3

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
        """
    ).fetchall()
    return {row["name"]: {"unique": bool(row["unique"])} for row in rows}
