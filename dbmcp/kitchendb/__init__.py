"""KitchenHQ database service (the ``dbmcp`` deployable).

Layout:
  config.py      - environment-derived settings (DB path, allowed hosts, API key header)
  db.py          - SQLite connection + row-fetch helpers
  schema.py      - runs schema.sql, seeds a fresh DB (no in-place migrations)
  seed.py        - first-run seed data
  validation.py  - pure input validation / normalization (no DB)
  models.py      - Pydantic request models
  tools/         - the data operations, each an MCP tool and/or a REST handler
  routes.py      - the /api/* REST surface
  server.py      - the FastAPI app

The repo-dir ``init_db.py`` is a thin compatibility shim over this package.
"""

from __future__ import annotations

from .config import DATABASE_PATH, get_database_path
from .schema import initialize_database
from .server import app, create_app

__all__ = ["app", "create_app", "initialize_database", "DATABASE_PATH", "get_database_path"]
