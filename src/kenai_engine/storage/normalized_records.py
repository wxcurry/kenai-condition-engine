"""Persistence helpers for normalized records."""

from __future__ import annotations

import sqlite3


def save_normalized_record(
    connection: sqlite3.Connection,
    record_type: str,
    observed_at: str,
    payload: str,
) -> int:
    cursor = connection.execute(
        "INSERT INTO normalized_records (record_type, observed_at, payload) VALUES (?, ?, ?)",
        (record_type, observed_at, payload),
    )
    connection.commit()
    return int(cursor.lastrowid)
