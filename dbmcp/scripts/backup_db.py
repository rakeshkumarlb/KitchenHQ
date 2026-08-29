"""Snapshot the KitchenHQ SQLite database for backup.

Uses sqlite3's online backup API (Connection.backup) rather than a raw file
copy, so a snapshot taken while dbmcp is running and writing does not risk
copying a half-written page.

Usage: python scripts/backup_db.py
Env vars: KITCHEN_DB_PATH (source, same default as init_db.py),
          KITCHEN_BACKUP_DIR (default: <db-dir>/backups),
          KITCHEN_BACKUP_RETENTION (default: 14, number of snapshots to keep)
"""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from init_db import DATABASE_PATH  # noqa: E402


def backup(source: Path, backup_dir: Path, retention: int) -> Path:
    if not source.exists():
        raise FileNotFoundError(f"No database found at {source}")
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = backup_dir / f"kitchen-{timestamp}.db"
    with sqlite3.connect(source) as source_connection, sqlite3.connect(destination) as destination_connection:
        source_connection.backup(destination_connection)
    prune(backup_dir, retention)
    return destination


def prune(backup_dir: Path, retention: int) -> None:
    snapshots = sorted(backup_dir.glob("kitchen-*.db"))
    for stale in snapshots[:-retention] if retention > 0 else []:
        stale.unlink()


def main() -> None:
    backup_dir = Path(os.environ.get("KITCHEN_BACKUP_DIR", DATABASE_PATH.parent / "backups"))
    retention = int(os.environ.get("KITCHEN_BACKUP_RETENTION", "14"))
    destination = backup(DATABASE_PATH, backup_dir, retention)
    print(f"Backed up {DATABASE_PATH} -> {destination}")


if __name__ == "__main__":
    main()
