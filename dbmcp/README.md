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

### Soft-deleted / unused endpoints

`POST /api/weekly-menu/plan` (and `add_weekly_menu_plan`) and `POST /api/weekly-menu/validate`
are commented out in `init_db.py` — nothing calls them (chatui builds the week
slot-by-slot; the agent uses the `validate_weekly_menu_policy` MCP tool, which stays).
The inventory-mutation REST routes (`POST /api/inventory`, `PATCH /api/inventory/{id}`,
`POST /api/inventory/{id}/discard`) remain: pytest exercises them and they mirror live
MCP tools, even though the read-only chatui Pantry page no longer calls them.

## Backups

`python scripts/backup_db.py` snapshots the live database (safe under concurrent writers) into `backups/`, keeping the most recent 14 by default. Schedule it daily, e.g. via Windows Task Scheduler or a host cron entry: `0 3 * * * KITCHEN_DB_PATH=/path/to/kitchen.db python /path/to/dbmcp/scripts/backup_db.py`.