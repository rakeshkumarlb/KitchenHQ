# KitchenHQ Chat UI

The chat UI connects to the long-lived Executive Chef agent over a small FastAPI service.

## Run with Docker Compose

From the repository root:

```powershell
docker compose up --build dbmcp chatui
```

Open `http://localhost:8080` and enter the `KITCHENHQ_API_KEY` value when prompted; the browser stores it in `localStorage` and sends it as `X-API-Key` on every request.

## Run locally

Install the root requirements, start the database MCP server, set `MCP_URL` and `KITCHENHQ_API_KEY` (must match the `dbmcp` service's key), then run:

```powershell
python -m uvicorn chatui.app:app --host 0.0.0.0 --port 8080
```