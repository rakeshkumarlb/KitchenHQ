"""Schema creation and first-run seeding.

The DDL itself lives in dbmcp/schema.sql (the human-readable source of truth, kept in
sync with db_design.md). This module just loads and runs it, then seeds a fresh DB.
"""

from __future__ import annotations

from pathlib import Path

from .config import get_database_path
from .db import connect
from .seed import seed_if_empty

_SCHEMA_SQL = (Path(__file__).resolve().parent.parent / "schema.sql").read_text(encoding="utf-8")


def initialize_database() -> None:
    """Create the schema (idempotent) and seed a fresh database.

    Assumes a database that is either empty or already on the current schema - there is
    no in-place migration of older layouts.
    """
    get_database_path().parent.mkdir(parents=True, exist_ok=True)
    with connect() as connection:
        connection.executescript(_SCHEMA_SQL)
        seed_if_empty(connection)
