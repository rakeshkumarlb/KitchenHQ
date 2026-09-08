"""SQLite connection helper and small row-fetch utilities."""

from __future__ import annotations

import sqlite3
from typing import Any

from .config import get_database_path


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(get_database_path())
    connection.row_factory = sqlite3.Row
    return connection


def fetch_record(table: str, record_id: int) -> dict[str, Any]:
    """Return a single row by id as a dict, raising ValueError if it does not exist."""
    with connect() as connection:
        row = connection.execute(f"SELECT * FROM {table} WHERE id = ?", (record_id,)).fetchone()
    if row is None:
        raise ValueError(f"No {table} record found for id {record_id}")
    return dict(row)


def fetch_record_in(connection: sqlite3.Connection, table: str, record_id: int) -> dict[str, Any]:
    """Like fetch_record but reuses an open connection; returns {} when not found."""
    row = connection.execute(f"SELECT * FROM {table} WHERE id = ?", (record_id,)).fetchone()
    return dict(row) if row is not None else {}
