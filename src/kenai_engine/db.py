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
        """
    )
    connection.commit()
