"""Environment-derived configuration for the KitchenHQ database service."""

from __future__ import annotations

import os
from pathlib import Path

# Default lives next to this package (dbmcp/kitchen.db), matching the historical
# behaviour of init_db.py.
_DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "kitchen.db"

_DEFAULT_ALLOWED_HOSTS = "localhost:18000,127.0.0.1:18000,dbmcp:18000,kitchenhq-db-mcp:18000"

API_KEY_HEADER = "X-API-Key"
PUBLIC_PATHS = {"/api/health"}


def get_database_path() -> Path:
    """Resolve the SQLite path from ``KITCHEN_DB_PATH`` on every call.

    Read dynamically (not cached at import) so tests can point each case at its own
    temp database by setting the env var before the first request.
    """
    return Path(os.environ.get("KITCHEN_DB_PATH", _DEFAULT_DB_PATH))


def mcp_allowed_hosts() -> list[str]:
    raw = os.environ.get("MCP_ALLOWED_HOSTS", _DEFAULT_ALLOWED_HOSTS)
    return [host.strip() for host in raw.split(",") if host.strip()]


# Import-time convenience for scripts that set KITCHEN_DB_PATH before importing
# (e.g. scripts/backup_db.py). Request handling always goes through get_database_path().
DATABASE_PATH = get_database_path()
