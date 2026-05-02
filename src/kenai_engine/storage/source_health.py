"""Persistence helpers for source health history."""

from __future__ import annotations

import sqlite3

SOURCE_HEALTH_STATUSES = frozenset({"ok", "placeholder", "error"})


def initialize_source_health_table(connection: sqlite3.Connection) -> None:
    """Create source health history storage if it does not exist."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS source_health (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            checked_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('ok', 'placeholder', 'error')),
            message TEXT NOT NULL
        )
        """
    )
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
