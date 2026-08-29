# KitchenHQ Chat UI

The chat UI connects to the long-lived Executive Chef agent over a small FastAPI service.

## Run with Docker Compose

From the repository root:

```powershell
docker compose up --build dbmcp chatui
```

Open `http://localhost:8080`.

## Run locally

Install the root requirements, start the database MCP server, set `MCP_URL`, then run:

```powershell
python -m uvicorn chatui.app:app --host 0.0.0.0 --port 8080
```