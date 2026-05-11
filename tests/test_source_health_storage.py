import sqlite3

from kenai_engine.storage.source_health import (
    initialize_source_health_table,
    list_latest_source_health,
    save_source_health,
)


def test_initialize_source_health_table_is_idempotent() -> None:
    connection = _connection()

    initialize_source_health_table(connection)
    initialize_source_health_table(connection)

    table = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = 'source_health'
        """
    ).fetchone()

    assert table is not None


def test_save_source_health_creates_table_when_missing() -> None:
    connection = _connection()

    row_id = save_source_health(
        connection,
        source="usgs",
        checked_at="2026-05-02T12:00:00+00:00",
        status="ok",
        message="Fetched live readings.",
    )

    stored = connection.execute(
        """
        SELECT id, source, checked_at, status, message
        FROM source_health
        WHERE id = ?
        """,
        (row_id,),
    ).fetchone()

    assert dict(stored) == {
        "id": row_id,
        "source": "usgs",
        "checked_at": "2026-05-02T12:00:00+00:00",
        "status": "ok",
        "message": "Fetched live readings.",
    }


def test_list_latest_source_health_returns_newest_record_per_source() -> None:
    connection = _connection()
    save_source_health(
        connection,
        source="usgs",
        checked_at="2026-05-02T12:00:00+00:00",
        status="error",
        message="Timeout.",
    )
    latest_usgs_id = save_source_health(
        connection,
        source="usgs",
        checked_at="2026-05-02T12:05:00+00:00",
        status="ok",
        message="Fetched live readings.",
    )
    fish_counts_id = save_source_health(
        connection,
        source="adfg_fish_counts",
        checked_at="2026-05-02T12:03:00+00:00",
        status="degraded",
        message="Using cached source content.",
    )

    rows = list_latest_source_health(connection)

    assert [row["id"] for row in rows] == [latest_usgs_id, fish_counts_id]
    assert [row["source"] for row in rows] == ["usgs", "adfg_fish_counts"]
    assert rows[0]["status"] == "ok"
    assert rows[1]["status"] == "degraded"


def test_save_source_health_rejects_unknown_status() -> None:
    connection = _connection()

    try:
        save_source_health(
            connection,
            source="usgs",
            checked_at="2026-05-02T12:00:00+00:00",
            status="stale",
            message="Unexpected status.",
        )
    except ValueError as error:
        assert str(error) == "Unknown source health status: stale"
    else:
        raise AssertionError("Expected ValueError for unknown source health status.")


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    return connection
