# KitchenHQ Database MCP Server

This folder is a standalone Docker package for the KitchenHQ SQLite MCP server.

## Build and run

From this folder:

```powershell
docker build -t kitchenhq-db-mcp .
docker run --rm -p 18000:18000 -v "${PWD}/data:/data" kitchenhq-db-mcp
```

The MCP endpoint is available at `http://localhost:8000/mcp`. The SQLite database is stored in the `data` folder on the host.

With Docker Compose, the host folder defaults to `./data`. Set `KITCHEN_DB_HOST_PATH` to use another local folder, for example in PowerShell:

```powershell
$env:KITCHEN_DB_HOST_PATH = 'C:/Users/Thinkpad/KitchenHQ-data'
docker compose up --build
```

The container always accesses the database as `/data/kitchen.db`; only the host-side location changes.

## Configuration

The container uses streamable HTTP by default. Override `MCP_TRANSPORT` with `stdio` when a Docker-aware MCP client launches the container over standard input/output. `KITCHEN_DB_PATH`, `MCP_HOST`, and `MCP_PORT` can also be overridden with environment variables.