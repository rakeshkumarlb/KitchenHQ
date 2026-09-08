# KitchenHQ Database MCP Server

This folder is a standalone Docker package for the KitchenHQ SQLite MCP server.

## Build and run

Every request (REST and MCP) requires an `X-API-Key` header matching `KITCHENHQ_API_KEY`; the server refuses to start without it set. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

From this folder:

```powershell
docker build -t kitchenhq-db-mcp .
docker run --rm -p 18000:18000 -e KITCHENHQ_API_KEY=your-key -v "${PWD}/data:/data" kitchenhq-db-mcp
```

The MCP endpoint is available at `http://localhost:18000/mcp`. The SQLite database is stored in the `data` folder on the host.

With Docker Compose, the host folder defaults to `./data`. Set `KITCHEN_DB_HOST_PATH` to use another local folder, for example in PowerShell:

```powershell
$env:KITCHEN_DB_HOST_PATH = 'C:/Users/Thinkpad/KitchenHQ-data'
docker compose up --build
```

The container always accesses the database as `/data/kitchen.db`; only the host-side location changes.

## Configuration

The container always serves over streamable HTTP. `KITCHENHQ_API_KEY` (required), `KITCHEN_DB_PATH`, `MCP_HOST`, and `MCP_PORT` can be overridden with environment variables.

### Email notifications

Moved out of dbmcp. The `send_*_email` tools, their SMTP config, and the body
builders now live in `agents/app/email/` — the agent is the only process
that sends mail, and none of it needed the database directly (it back-fills the saved
menu / shopping list over this service's REST API). dbmcp has no `SMTP_*` variables
and no `/api/notifications/*` routes.

### Code layout

`init_db.py` is a thin compatibility shim (`uvicorn init_db:app`, `python init_db.py`,
`from init_db import DATABASE_PATH`). The implementation is the `kitchendb/` package:
`config` / `db` / `schema` / `seed` / `validation` / `models`, `tools/` (data operations
by domain — each an MCP tool and/or a REST handler), `routes.py`, and `server.py`
(`create_app()`). The fresh-start DDL is `schema.sql`. `constants.py` (day / meal-type
vocabulary + ordering) is a vendored copy of `../shared/constants.py` — edit the shared
file and run `python ../shared/sync.py`; a test fails if this copy drifts. Those values
are also served to clients in the `constants` block of `GET /api/dashboard`. There is no
in-place migration of older databases — a database is assumed empty or already on the
current schema.

The inventory-mutation REST routes (`POST /api/inventory`, `PATCH /api/inventory/{id}`,
`POST /api/inventory/{id}/discard`) are kept: pytest exercises them and they mirror live
MCP tools, even though the read-only chatui Pantry page no longer calls them.

## Backups

`python scripts/backup_db.py` snapshots the live database (safe under concurrent writers) into `backups/`, keeping the most recent 14 by default. Schedule it daily, e.g. via Windows Task Scheduler or a host cron entry: `0 3 * * * KITCHEN_DB_PATH=/path/to/kitchen.db python /path/to/dbmcp/scripts/backup_db.py`.