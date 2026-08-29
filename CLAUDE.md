# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository overview

KitchenHQ is three independently deployable services orchestrated by the root `docker-compose.yml`:

| Service | Dir | Language | Port | Role |
|---|---|---|---|---|
| `dbmcp` | `dbmcp/` | Python (FastAPI + FastMCP) | 18000 | Owns the SQLite database. Exposes the same data operations twice: as plain REST (`/api/*`) and as MCP tools (`/mcp`, via `mcp.streamable_http_app()` mounted on the same FastAPI app). |
| `chatui` | `chatui/` | React (Vite) + Python (FastAPI) | 8080 | React SPA built to `chatui/dist` and served by a FastAPI backend that proxies CRUD calls to `dbmcp` and hosts the `/api/chat` endpoint. |
| `executivechef_agent` | `executivechef_agent/` | Python (LangChain) | n/a (worker) | LangChain agents (Executive Chef, Sous Chef, Pantry Manager) that call `dbmcp` over MCP. `worker.py` runs all three roles on an APScheduler cron loop; `agent.py` run standalone gives one interactive terminal REPL with the Executive Chef only. |

There is no top-level package manager tying the three together — each has its own `requirements.txt` (Python, pinned) or `package.json` (Node), and there is a root `requirements.txt` used only for building the `chatui` Docker image (see Architecture below).

Every service requires `KITCHENHQ_API_KEY` to be set (see Commands) — all three refuse to start without it.

**Linting/formatting are not configured anywhere in this repo** (no ESLint/Prettier config, no `pyproject.toml`). `dbmcp` has pytest smoke tests (`dbmcp/tests/`); `chatui` and `executivechef_agent` have none.

## Commands

### Full stack (Docker Compose, from repo root)
```powershell
docker compose up --build
```
Starts `dbmcp` (18000), `chatui` (8080), and `agent-worker`. Requires a root `.env` (copy from `.env.example`) with `KITCHENHQ_API_KEY` set — `docker-compose.yml` fails fast via `${KITCHENHQ_API_KEY:?...}` if it's missing. `agent-worker` and `chatui` also read `executivechef_agent/.env` (copy from `executivechef_agent/.env.example`; set `OPENAI_API_KEY` or `LLM_PROVIDER=ollama`, and the same `KITCHENHQ_API_KEY`).

To run a subset: `docker compose up --build dbmcp chatui`.

Set `KITCHEN_DB_HOST_PATH` in root `.env` to relocate the SQLite volume (defaults to `./data`). `KITCHEN_TIMEZONE` sets the scheduler's `TZ` (default `Asia/Kolkata`).

### dbmcp, standalone
```powershell
cd dbmcp
pip install -r requirements.txt
$env:KITCHENHQ_API_KEY = "..."
python init_db.py            # runs uvicorn on :18000, creates/migrates kitchen.db on startup
```
Or via its own Dockerfile: `docker build -t kitchenhq-db-mcp .` then `docker run --rm -p 18000:18000 -e KITCHENHQ_API_KEY=... -v "${PWD}/data:/data" kitchenhq-db-mcp`. Every request (REST and MCP) needs an `X-API-Key: <KITCHENHQ_API_KEY>` header.

Tests: `pip install -r requirements-dev.txt && pytest tests/` (spins up a temp SQLite DB per test via `KITCHEN_DB_PATH`, no live server needed).

Backups: `python scripts/backup_db.py` snapshots the live DB into `backups/` (uses SQLite's online backup API, safe under concurrent writers), keeping the last 14 by default — see `dbmcp/README.md` for scheduling it.

### executivechef_agent, standalone
```powershell
cd executivechef_agent
pip install -r requirements.txt
python agent.py     # interactive terminal chat with the Executive Chef only
python worker.py     # all three roles + cron schedule, no terminal I/O
```
Requires `dbmcp` reachable at `MCP_URL` (default `http://localhost:18000/mcp` when run outside Docker; the Docker Compose network uses the service name `dbmcp`) and `KITCHENHQ_API_KEY` matching `dbmcp`'s.

### chatui, standalone
```powershell
cd chatui
npm install
npm run dev          # Vite dev server; the FastAPI backend below must run separately for /api/* to work
npm run build         # outputs chatui/dist, which app.py serves as static files
```
```powershell
# from repo root, with root requirements.txt installed and KITCHENHQ_API_KEY set
python -m uvicorn chatui.app:app --host 0.0.0.0 --port 8080
```
On first load the browser prompts for the access key (same `KITCHENHQ_API_KEY` value) and stores it in `localStorage`; a 401 from any `/api/*` call clears it and re-prompts.

## Architecture

### dbmcp is the single source of truth for the schema
`dbmcp/init_db.py` is one file that does three things: defines the SQLite schema and self-migration (`initialize_database()`, run on FastAPI `lifespan` startup — idempotent `CREATE TABLE IF NOT EXISTS` plus `ALTER TABLE ... ADD COLUMN` backfills and one-time seed data), defines the data operations as plain functions decorated with `@mcp.tool()`, and re-exposes almost every one of those functions as a FastAPI REST route (thin Pydantic-validated wrappers that call the same function). `dbmcp/db_design.md` documents the same schema for humans — keep it in sync when changing `initialize_database()`, but if the two ever disagree, `init_db.py` is authoritative.

Two write paths (`add_detailed_prep_schedule`/`acknowledge_prep_schedule` for prep tasks, `create_shopping_list`/`acknowledge_shopping_list` for shopping) follow a propose-then-acknowledge pattern: the propose step never touches `inventory`, and the acknowledge step is idempotent via a required `acknowledgement_key` recorded in `inventory_transactions.idempotency_key` — replays return `{"replayed": True}` instead of double-deducting/adding stock. Preserve this pattern when extending inventory-affecting flows.

`validate_weekly_menu_policy` encodes the household's menu rules (no egg/meat/fish in lunches, five distinct weekday lunches) and is called both standalone (`/api/weekly-menu/validate`) and internally by `add_weekly_menu_plan` before any row is written, so a full week is saved atomically or not at all.

A `@app.middleware("http")` function (`require_api_key`) sits in front of every route except `/api/health`, checking `X-API-Key` against `KITCHENHQ_API_KEY`. Because it's outer FastAPI middleware, it also covers the mounted `mcp.streamable_http_app()` at `/mcp` — there's no separate MCP-layer auth.

### executivechef_agent: one agent class, three role configurations
`agent.py`'s `KitchenHQAgent` is instantiated per role (`executive_chef`, `sous_chef`, `pantry_manager`). All three share the same base `SYSTEM_PROMPT` (loaded from `prompt.md` plus operating rules) but get a different `ROLE_PROMPTS` fragment appended and a different MCP tool subset via `ROLE_TOOLS` (executive_chef gets every tool; sous_chef and pantry_manager are restricted to a fixed allowlist filtered from the tools `MultiServerMCPClient` discovers from `dbmcp`, connecting with an `X-API-Key` header). Sous chef and pantry manager also get a structured `response_format` (`SousChefResult`/`PantryManagerResult`) so their scheduled-job output can be validated with `model_validate` in `run_scheduled`.

`worker.py` builds all three role instances and registers cron jobs via `configure_scheduler()` (weekly menu Saturdays, Sunday/nightly/morning prep, daily pantry check). Each scheduled run posts a best-effort telemetry record to `dbmcp`'s `/api/agent-runs` regardless of success/failure — a telemetry-post failure is swallowed so it never fails the job itself.

Chat history is not kept in process memory: `KitchenHQAgent.ask()` loads/saves each session's message list from/to `dbmcp`'s `chat_sessions` table (`_load_history`/`_save_history`, module-level helpers near the top of `agent.py`), serializing with `langchain_core.messages.messages_to_dict`/`messages_from_dict`. Scheduled jobs call `ask(..., remember=False)`, which skips history entirely — each scheduled run is a fresh one-shot request.

`agent.py` run directly (`__main__`) only starts a single `executive_chef` agent for an interactive terminal loop; its own scheduler wiring is currently commented out, so autonomous jobs only run via `worker.py`/the `agent-worker` container.

### chatui runs its own separate agent instance
`chatui/app.py` does not call `agent-worker` over the network for chat — it imports `KitchenHQAgent` directly from `executivechef_agent/agent.py` via a `sys.path` insert (`ROOT / "executivechef_agent"`) and starts its own `executive_chef` instance in its FastAPI `lifespan`. This means chat conversations are served by a process distinct from the scheduled autonomous jobs in `agent-worker`, but since both go through the same `dbmcp`-backed `chat_sessions` table (see above), history for a given `session_id` is consistent regardless of which process handles a given turn, and survives restarts. Everything else in `chatui/app.py` (`/api/dashboard`, `/api/inventory/*`, `/api/weekly-menu/*`, `/api/prep-schedule/*`, `/api/shopping-lists/*`) is a thin proxy to `dbmcp`'s REST API at `DB_API_URL` (default `http://dbmcp:18000`), forwarding the `X-API-Key` header it received from the browser.

`chatui`'s own `/api/*` routes (except `/api/health`) are behind the same `require_api_key` middleware pattern as `dbmcp`, since real users hit them directly from the browser. The React app has a key-entry gate (`src/components/AccessGate.jsx`) in front of everything else in `App.jsx`; `src/services/api.js` attaches the stored key to every request and clears it on a 401.

The React app (`chatui/src`) has no router — `App.jsx` holds `page` in `useState` and switch-renders `Dashboard`/`Pantry`/`WeeklyMenu`/`TaskList`/`Chat`, all fed from one `/api/dashboard` payload fetched on mount and patched locally after each mutation (see `src/services/api.js` for the full REST surface it calls).

### Still prototype-grade
No multi-user auth (one shared key for the whole household, not per-user accounts); SQLite with no replication (only local timestamped snapshots via `dbmcp/scripts/backup_db.py`); no CI; `chatui` and `executivechef_agent` have no automated tests.
