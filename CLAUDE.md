# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository overview

KitchenHQ is three independently deployable services orchestrated by the root `docker-compose.yml`:

| Service | Dir | Language | Port | Role |
|---|---|---|---|---|
| `dbmcp` | `dbmcp/` | Python (FastAPI + FastMCP) | 18000 | Owns the SQLite database. Exposes the same data operations twice: as plain REST (`/api/*`) and as MCP tools (`/mcp`, via `mcp.streamable_http_app()` mounted on the same FastAPI app). |
| `chatui` | `chatui/` | React (Vite) + Python (FastAPI) | 8080 | React SPA built to `chatui/dist` and served by a FastAPI backend that proxies CRUD calls to `dbmcp` and hosts the `/api/chat` endpoint. |
| `executivechef_agent` | `executivechef_agent/` | Python (LangChain) | n/a (worker) | LangChain agents (Executive Chef, Sous Chef, Pantry Manager) that call `dbmcp` over MCP. `worker.py` runs all three roles on an APScheduler cron loop; `agent.py` run standalone gives one interactive terminal REPL with the Executive Chef only. |

There is no top-level package manager tying the three together — each has its own `requirements.txt` (Python) or `package.json` (Node), and there is a root `requirements.txt` used only for building the `chatui` Docker image (see Architecture below).

**No automated tests, linters, or formatters are currently configured anywhere in this repo** (no `pytest`/test files, no ESLint/Prettier config, no `pyproject.toml`). If you add tooling, wire it into this file.

## Commands

### Full stack (Docker Compose, from repo root)
```powershell
docker compose up --build
```
Starts `dbmcp` (18000), `chatui` (8080), and `agent-worker`. `agent-worker` and `chatui` both read `executivechef_agent/.env` (copy from `executivechef_agent/.env.example`; at minimum set `OPENAI_API_KEY` or set `LLM_PROVIDER=ollama`).

To run a subset: `docker compose up --build dbmcp chatui`.

Set `KITCHEN_DB_HOST_PATH` (PowerShell: `$env:KITCHEN_DB_HOST_PATH = 'C:/path'`) to relocate the SQLite volume; it defaults to `./data` next to `docker-compose.yml`. `KITCHEN_TIMEZONE` sets the scheduler's `TZ` (default `Asia/Kolkata`).

### dbmcp, standalone
```powershell
cd dbmcp
pip install -r requirements.txt
python init_db.py            # runs uvicorn on :18000, creates/migrates kitchen.db on startup
```
Or via its own Dockerfile: `docker build -t kitchenhq-db-mcp .` then `docker run --rm -p 18000:18000 -v "${PWD}/data:/data" kitchenhq-db-mcp`. `MCP_TRANSPORT=stdio` switches the FastMCP layer to stdio for Docker-aware MCP clients.

### executivechef_agent, standalone
```powershell
cd executivechef_agent
pip install -r requirements.txt
python agent.py     # interactive terminal chat with the Executive Chef only
python worker.py     # all three roles + cron schedule, no terminal I/O
```
Requires `dbmcp` reachable at `MCP_URL` (default `http://localhost:18000/mcp` when run outside Docker; the Docker Compose network uses the service name `dbmcp`).

### chatui, standalone
```powershell
cd chatui
npm install
npm run dev          # Vite dev server; the FastAPI backend below must run separately for /api/* to work
npm run build         # outputs chatui/dist, which app.py serves as static files
```
```powershell
# from repo root, with root requirements.txt installed
python -m uvicorn chatui.app:app --host 0.0.0.0 --port 8080
```

## Architecture

### dbmcp is the single source of truth for the schema
`dbmcp/init_db.py` is one file that does three things: defines the SQLite schema and self-migration (`initialize_database()`, run on FastAPI `lifespan` startup — idempotent `CREATE TABLE IF NOT EXISTS` plus `ALTER TABLE ... ADD COLUMN` backfills and one-time seed data), defines the data operations as plain functions decorated with `@mcp.tool()`, and re-exposes almost every one of those functions as a FastAPI REST route (thin Pydantic-validated wrappers that call the same function). `dbmcp/db_design.md` is a stale hand-written description of an earlier schema (missing `shopping_lists`, `shopping_items`, `inventory_transactions`, `agent_runs`, and several columns) — treat `init_db.py` as authoritative, not that file.

Two write paths (`add_detailed_prep_schedule`/`acknowledge_prep_schedule` for prep tasks, `create_shopping_list`/`acknowledge_shopping_list` for shopping) follow a propose-then-acknowledge pattern: the propose step never touches `inventory`, and the acknowledge step is idempotent via a required `acknowledgement_key` recorded in `inventory_transactions.idempotency_key` — replays return `{"replayed": True}` instead of double-deducting/adding stock. Preserve this pattern when extending inventory-affecting flows.

`validate_weekly_menu_policy` encodes the household's menu rules (no egg/meat/fish in lunches, five distinct weekday lunches) and is called both standalone (`/api/weekly-menu/validate`) and internally by `add_weekly_menu_plan` before any row is written, so a full week is saved atomically or not at all.

### executivechef_agent: one agent class, three role configurations
`agent.py`'s `KitchenHQAgent` is instantiated per role (`executive_chef`, `sous_chef`, `pantry_manager`). All three share the same base `SYSTEM_PROMPT` (loaded from `prompt.md` plus operating rules) but get a different `ROLE_PROMPTS` fragment appended and a different MCP tool subset via `ROLE_TOOLS` (executive_chef gets every tool; sous_chef and pantry_manager are restricted to a fixed allowlist filtered from the tools `MultiServerMCPClient` discovers from `dbmcp`). Sous chef and pantry manager also get a structured `response_format` (`SousChefResult`/`PantryManagerResult`) so their scheduled-job output can be validated with `model_validate` in `run_scheduled`.

`worker.py` builds all three role instances and registers cron jobs via `configure_scheduler()` (weekly menu Saturdays, Sunday/nightly/morning prep, daily pantry check). Each scheduled run posts a best-effort telemetry record to `dbmcp`'s `/api/agent-runs` regardless of success/failure — a telemetry-post failure is swallowed so it never fails the job itself.

`agent.py` run directly (`__main__`) only starts a single `executive_chef` agent for an interactive terminal loop; its own scheduler wiring is currently commented out, so autonomous jobs only run via `worker.py`/the `agent-worker` container.

### chatui runs its own separate agent instance
`chatui/app.py` does not call `agent-worker` over the network for chat — it imports `KitchenHQAgent` directly from `executivechef_agent/agent.py` via a `sys.path` insert (`ROOT / "executivechef_agent"`) and starts its own `executive_chef` instance in its FastAPI `lifespan`. This means chat conversations are served by a process distinct from the scheduled autonomous jobs in `agent-worker`, and chat history (`_messages_by_session`) lives only in that process's memory — it is lost on restart and not shared across chatui replicas. Everything else in `chatui/app.py` (`/api/dashboard`, `/api/inventory/*`, `/api/weekly-menu/*`, `/api/prep-schedule/*`, `/api/shopping-lists/*`) is a thin proxy to `dbmcp`'s REST API at `DB_API_URL` (default `http://dbmcp:18000`).

The React app (`chatui/src`) has no router — `App.jsx` holds `page` in `useState` and switch-renders `Dashboard`/`Pantry`/`WeeklyMenu`/`TaskList`/`Chat`, all fed from one `/api/dashboard` payload fetched on mount and patched locally after each mutation (see `src/services/api.js` for the full REST surface it calls).

### Legacy root-level prototype (predates the three-service split)
`main.py`, `main copy.py`, `mcp_server.py`, and `prompts.py` at the repo root are an earlier Slack-bot prototype (Ollama-backed, `slack_bolt`) with its own standalone MCP server, superseded by the `dbmcp`/`executivechef_agent`/`chatui` split described above. They are not referenced by `docker-compose.yml` or either service's Dockerfile. `.vscode/mcp.json` still points VS Code's MCP client at this legacy root `mcp_server.py`, not `dbmcp/init_db.py` — treat these root files as historical unless the user says otherwise, and don't assume changes to `dbmcp` are reflected there.

### Production-hardening context
The user's stated goal is to take this from prototype to production. Things visibly still prototype-grade, worth flagging before extending rather than silently working around: no auth on any REST/MCP/chat endpoint; chat session state is in-memory-only (see above); SQLite with no backup/replication story; secrets live in plain `.env` files committed alongside `.env.example`; no tests; the root `requirements.txt` (used only by `chatui`'s Docker build) and `executivechef_agent/requirements.txt` are two separate unpinned dependency lists that can drift.
