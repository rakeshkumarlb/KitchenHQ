"""Compatibility entry point for the KitchenHQ database service.

The implementation now lives in the ``kitchendb/`` package. This module keeps the
historical import path working - ``uvicorn init_db:app``, ``from init_db import
DATABASE_PATH`` (scripts/backup_db.py), and ``import init_db`` (tests) - and provides
the ``python init_db.py`` dev runner.
"""

from __future__ import annotations

import os

from kitchendb import DATABASE_PATH, app, get_database_path, initialize_database
from kitchendb.tools.weekly_menu import validate_weekly_menu_policy

__all__ = [
    "app",
    "initialize_database",
    "DATABASE_PATH",
    "get_database_path",
    "validate_weekly_menu_policy",
]


if __name__ == "__main__":
    import uvicorn

    initialize_database()
    uvicorn.run(app, host=os.environ.get("MCP_HOST", "0.0.0.0"), port=int(os.environ.get("MCP_PORT", "18000")))
