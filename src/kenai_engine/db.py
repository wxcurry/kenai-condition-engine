"""Small SQLite database layer for engine state."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from kenai_engine.condition_variables import CONDITION_VARIABLE_ROWS


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

        CREATE TABLE IF NOT EXISTS condition_variables (
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
            status TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT 'general',
            kenai_relevance TEXT NOT NULL DEFAULT '',
            collection_method TEXT NOT NULL DEFAULT '',
            calculation_method TEXT NOT NULL DEFAULT '',
            proxy_method TEXT NOT NULL DEFAULT '',
            update_frequency TEXT NOT NULL DEFAULT '',
            limitations TEXT NOT NULL DEFAULT ''
        );

        CREATE UNIQUE INDEX IF NOT EXISTS ux_condition_variables_name
        ON condition_variables (name);
        """
    )
    _ensure_condition_variable_columns(connection)
    connection.executemany(
        """
        INSERT OR REPLACE INTO condition_variables (
            name,
            description,
            data_type,
            unit,
            valid_range,
            default_value,
            source_url,
            source_title,
            source_organization,
            date_accessed,
            code_locations,
            calculation_notes,
            status,
            display_name,
            category,
            kenai_relevance,
            collection_method,
            calculation_method,
            proxy_method,
            update_frequency,
            limitations
        )
        VALUES (
            :name,
            :description,
            :data_type,
            :unit,
            :valid_range,
            :default_value,
            :source_url,
            :source_title,
            :source_organization,
            :date_accessed,
            :code_locations,
            :calculation_notes,
            :status,
            :display_name,
            :category,
            :kenai_relevance,
            :collection_method,
            :calculation_method,
            :proxy_method,
            :update_frequency,
            :limitations
        )
        """,
        CONDITION_VARIABLE_ROWS,
    )
    connection.commit()


def _ensure_condition_variable_columns(connection: sqlite3.Connection) -> None:
    """Add condition-variable metadata columns to existing SQLite databases."""

    existing = {
        _pragma_column_name(row)
        for row in connection.execute("PRAGMA table_info(condition_variables)").fetchall()
    }
    additions = {
        "display_name": "TEXT NOT NULL DEFAULT ''",
        "category": "TEXT NOT NULL DEFAULT 'general'",
        "kenai_relevance": "TEXT NOT NULL DEFAULT ''",
        "collection_method": "TEXT NOT NULL DEFAULT ''",
        "calculation_method": "TEXT NOT NULL DEFAULT ''",
        "proxy_method": "TEXT NOT NULL DEFAULT ''",
        "update_frequency": "TEXT NOT NULL DEFAULT ''",
        "limitations": "TEXT NOT NULL DEFAULT ''",
    }
    for column_name, column_definition in additions.items():
        if column_name not in existing:
            connection.execute(
                f"ALTER TABLE condition_variables ADD COLUMN {column_name} {column_definition}"
            )


def _pragma_column_name(row: sqlite3.Row | tuple[object, ...]) -> str:
    if isinstance(row, sqlite3.Row):
        return str(row["name"])
    return str(row[1])
