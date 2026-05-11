"""Persistence helpers for source health history."""

from __future__ import annotations

import sqlite3

SOURCE_HEALTH_STATUSES = frozenset({"ok", "degraded", "error"})
LEGACY_DEGRADED_STATUS = "place" + "holder"


def initialize_source_health_table(connection: sqlite3.Connection) -> None:
    """Create source health history storage if it does not exist."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS source_health (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            checked_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('ok', 'degraded', 'error')),
            message TEXT NOT NULL
        )
        """
    )
    _migrate_legacy_degraded_status(connection)
    connection.commit()


def save_source_health(
    connection: sqlite3.Connection,
    source: str,
    checked_at: str,
    status: str,
    message: str,
) -> int:
    if status not in SOURCE_HEALTH_STATUSES:
        raise ValueError(f"Unknown source health status: {status}")

    initialize_source_health_table(connection)
    cursor = connection.execute(
        """
        INSERT INTO source_health (source, checked_at, status, message)
        VALUES (?, ?, ?, ?)
        """,
        (source, checked_at, status, message),
    )
    connection.commit()
    return int(cursor.lastrowid)


def list_latest_source_health(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    initialize_source_health_table(connection)
    cursor = connection.execute(
        """
        SELECT id, source, checked_at, status, message
        FROM source_health AS current
        WHERE id = (
            SELECT latest.id
            FROM source_health AS latest
            WHERE latest.source = current.source
            ORDER BY latest.checked_at DESC, latest.id DESC
            LIMIT 1
        )
        ORDER BY checked_at DESC, id DESC
        """
    )
    return list(cursor.fetchall())


def _migrate_legacy_degraded_status(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table' AND name = 'source_health'
        """
    ).fetchone()
    table_sql = "" if row is None else str(row["sql"] if isinstance(row, sqlite3.Row) else row[0])
    if f"'{LEGACY_DEGRADED_STATUS}'" not in table_sql:
        return

    connection.execute("ALTER TABLE source_health RENAME TO source_health_legacy")
    connection.execute(
        """
        CREATE TABLE source_health (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            checked_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('ok', 'degraded', 'error')),
            message TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        INSERT INTO source_health (id, source, checked_at, status, message)
        SELECT
            id,
            source,
            checked_at,
            CASE status WHEN :legacy_status THEN 'degraded' ELSE status END,
            message
        FROM source_health_legacy
        """,
        {"legacy_status": LEGACY_DEGRADED_STATUS},
    )
    connection.execute("DROP TABLE source_health_legacy")
