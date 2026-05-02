"""Persistence helpers for normalized records."""

from __future__ import annotations

import sqlite3


def save_normalized_record(
    connection: sqlite3.Connection,
    record_type: str,
    observed_at: str,
    payload: str,
) -> int:
    existing = connection.execute(
        """
        SELECT id
        FROM normalized_records
        WHERE record_type = ? AND observed_at = ? AND payload = ?
        LIMIT 1
        """,
        (record_type, observed_at, payload),
    ).fetchone()
    if existing is not None:
        return int(existing["id"])

    cursor = connection.execute(
        "INSERT INTO normalized_records (record_type, observed_at, payload) VALUES (?, ?, ?)",
        (record_type, observed_at, payload),
    )
    connection.commit()
    return int(cursor.lastrowid)


def list_normalized_records(
    connection: sqlite3.Connection,
    record_type: str,
    limit: int = 50,
) -> list[sqlite3.Row]:
    cursor = connection.execute(
        """
        SELECT id, record_type, observed_at, payload
        FROM normalized_records
        WHERE record_type = ?
        ORDER BY observed_at DESC, id DESC
        LIMIT ?
        """,
        (record_type, limit),
    )
    return list(cursor.fetchall())
