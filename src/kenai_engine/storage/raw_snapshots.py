"""Persistence helpers for raw source snapshots."""

from __future__ import annotations

import sqlite3


def save_raw_snapshot(
    connection: sqlite3.Connection,
    source: str,
    payload: str,
    fetched_at: str,
) -> int:
    cursor = connection.execute(
        "INSERT INTO raw_snapshots (source, fetched_at, payload) VALUES (?, ?, ?)",
        (source, fetched_at, payload),
    )
    connection.commit()
    return int(cursor.lastrowid)
