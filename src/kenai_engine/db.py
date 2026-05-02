"""Small SQLite database layer for engine state."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection and ensure the parent directory exists."""

    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(connection: sqlite3.Connection) -> None:
    """Create MVP tables if they do not exist."""

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS raw_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            payload TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS normalized_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_type TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            payload TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_raw_snapshots_source_fetched_at_id
        ON raw_snapshots (source, fetched_at DESC, id DESC);

        CREATE INDEX IF NOT EXISTS idx_normalized_records_type_observed_at_id
        ON normalized_records (record_type, observed_at DESC, id DESC);
        """
    )
    connection.execute(
        """
        DELETE FROM normalized_records
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM normalized_records
            GROUP BY record_type, observed_at, payload
        )
        """
    )
    connection.executescript(
        """

        CREATE UNIQUE INDEX IF NOT EXISTS ux_normalized_records_type_observed_payload
        ON normalized_records (record_type, observed_at, payload);
        """
    )
    connection.commit()
