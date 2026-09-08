# KitchenHQ

**An AI sous-chef for the whole household.** KitchenHQ plans your week's meals, batches your prep, keeps your pantry honest, and writes your shopping list — automatically, on a schedule, or on demand from a chat window.

It's a small, self-hostable stack of three services you run with one `docker compose up`. A team of LLM agents does the thinking; a SQLite database is the single source of truth; a clean React UI is how you steer it.

---

## Why it exists

Feeding a family is a logistics problem that repeats every single day: *what are we eating, what needs defrosting tonight, what's about to run out, what goes on the list.* KitchenHQ turns that recurring load into a set of background jobs and a conversation.

- **Plan once a week, not every morning.** The Executive Chef agent reads your inventory and household preferences and writes a full Monday–Sunday menu — breakfast, lunch, snack, dinner — that respects your dietary rules and 20-minute weekday prep cap.
- **Wake up to a plan, not a decision.** Nightly and morning jobs turn each day's menu into an ordered, time-capped prep checklist and a parallel cooking plan.
- **The pantry stays truthful.** Completing a prep task deducts exactly what it used from inventory. When stock dips below its threshold, the Pantry Manager drafts a shopping list — merged, de-duplicated, ready to check off.
- **Everything is inspectable.** Every scheduled run is recorded with its tool calls, output, and success/failure. Nothing happens in a black box.

---

## Highlights

| | |
|---|---|
| 🧑‍🍳 **Three specialist agents** | Executive Chef (weekly menu), Sous Chef (prep & cooking plans), Pantry Manager (shopping) — each with its own lane, sharing one toolset over MCP. |
| ⏰ **In-process cron** | 6 jobs on an `AsyncIOScheduler` inside the API process — no extra worker container, no network hop. Fire any of them on demand from the UI. |
| 💬 **Chat with the chef** | Ask for a swap, a substitution, a "what can I make with what's in the fridge" — full conversation history, persisted, resumable. |
| 📧 **Agent-driven email** | Opt-in SMTP: the agents email you the weekly plan, tonight's prep, or the shopping list. Never automatic, never blocks a job. |
| 🔒 **One-key auth** | A single shared secret gates every REST and MCP request across all three services. |
| 🗄️ **Honest inventory** | Propose-then-acknowledge writes with idempotency keys — replays never double-count stock. |
| 📦 **Self-contained** | Pinned dependencies, SQLite with online backups, no cloud services required (bring your own OpenAI key, or run Ollama locally). |

---

## Architecture

Three independently deployable services, orchestrated by the root `docker-compose.yml`:

```
  ┌──────────────────────────────────────────────────────────────────────┐
  │  Browser  →  chatui  :8080     React SPA + thin FastAPI proxy         │
  └────────┬────────────────────────────────────────────┬────────────────┘
           │ REST  /api/*                               │ REST  /api/chat
           │ dashboard · pantry · weekly menu ·         │      /api/automations/*
           │ tasks · profile · CRUD                     │ chat w/ Executive Chef,
           │                                            │ run a job now, run history
           │                                            ▼
           │                  ┌──────────────────────────────────────────────┐
           │                  │  agent-api  :8090                            │
           │                  │  LangChain agent · FastAPI · APScheduler     │
           │                  │  (6 cron jobs, in-process)                   │
           │                  │                                             │
           │                  │  ── LOCAL tools (built fresh per request) ── │
           │                  │   get_job_context ....... date math + the    │
           │                  │                           job's intent /     │
           │                  │                           target weekdays    │
           │                  │   send_prep_task_email     ┐                 │
           │                  │   send_weekly_plan_email   ├─ SMTP ─▶ mail   │
           │                  │   send_shopping_list_email ┘   (opt-in)      │
           │                  └───────┬─────────────────────────┬────────────┘
           │            MCP  /mcp     │              REST  /api  │  (email only:
           │   ── REMOTE tools ──     │        recipient address, saved menu, │
           │   inventory · weekly     │        pending shopping items — back- │
           │   menu · prep · shopping │        fill so the agent's call stays │
           │   · preferences · …      │        small)                        │
           ▼                          ▼                          ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │  dbmcp  :18000     FastAPI + FastMCP — owns kitchen.db (SQLite)       │
  │  every data operation exposed twice:   REST /api/*    and    /mcp     │
  └──────────────────────────────────────────────────────────────────────┘
```

- **chatui** is a pure REST client. It calls **dbmcp** directly for all CRUD/read data (`/api/dashboard` and friends) and **agent-api** for anything that needs the LLM (chat, "run job now"). It holds no LangChain/MCP dependency.
- **agent-api** reaches **dbmcp** over **MCP** (`/mcp`) for every data operation the agent performs. The only REST calls it makes to dbmcp are inside the email tools — fetching the recipient address and back-filling the saved menu / pending shopping list so the model's tool call can stay minimal.
- The agent's toolset each run = **remote MCP tools** (from dbmcp) + **local in-process tools**: `get_job_context` (the authoritative source for date math and *why* a scheduled run fired) and the three `send_*_email` tools (which talk SMTP directly to your mail server; disabled = harmless no-op).

| Service | Dir | Stack | Port | Role |
|---|---|---|---|---|
| **dbmcp** | `dbmcp/` | Python · FastAPI · FastMCP | 18000 | Owns the SQLite database and its schema/migrations. Exposes every data operation twice — as REST (`/api/*`) and as MCP tools (`/mcp`) — from one FastAPI app. |
| **agent-api** | `agents/` | Python · LangChain · APScheduler | 8090 | The only process that talks to the LLM and to `dbmcp` over MCP. Serves `/chat` and `/invoke/{job}`, and runs the cron jobs in-process. Every request builds and disposes its own LLM/MCP connections — nothing outlives a single call. |
| **chatui** | `chatui/` | React (Vite) · FastAPI | 8080 | React SPA served by a thin FastAPI backend that proxies CRUD to `dbmcp` and chat/automation calls to `agent-api`. Holds no LangChain/MCP dependency of its own. |

**Design principle — bounded connection lifetime.** `agent-api` builds a fresh LLM client and MCP toolset per request and disposes them in a `finally` block. There is no long-lived agent object and no cross-call lock; concurrent chats and jobs run fully independently. (This is a deliberate fix for a real incident where a stale long-lived Ollama connection wedged the host.)

---

## Quick start

**Prerequisites:** Docker + Docker Compose, and either an OpenAI API key or a local Ollama.

```bash
git clone <this-repo> KitchenHQ
cd KitchenHQ

# 1. Root env — shared secret for all three services
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(32))"   # paste into KITCHENHQ_API_KEY=

# 2. Agent env — LLM provider
cp agents/.env.example agents/.env
#   set OPENAI_API_KEY=...   (or LLM_PROVIDER=ollama + OLLAMA_BASE_URL=...)
#   set the same KITCHENHQ_API_KEY value

# 3. Go
docker compose up --build
```

Then open **http://localhost:8080**, enter the `KITCHENHQ_API_KEY` value when prompted (stored in `localStorage`, sent as `X-API-Key` on every request), and you're in.

Run a subset while iterating: `docker compose up --build dbmcp chatui`.

### Optional: email notifications

Set `SMTP_HOST` (and creds) in the root `.env` to let the agents email the address on your Profile page — the weekly plan, tonight's prep, the shopping list. There is **no** automatic send: a job asks for an email as one of its steps, and a disabled toggle or unset host simply comes back as `{"sent": false}` without failing the job. A Gmail app password works (`smtp.gmail.com:587`).

---

## The agents

Prompts live in `agents/prompts/*.md`. `system.md` is a role-neutral shared base (household context, dietary rules); each role fragment is appended as "Your role". Job-specific detail (which day, which meals, the time cap) lives separately in `agents/app/jobs.py`, not the prompts.

| Role | Owns | Structured output |
|---|---|---|
| **Executive Chef** | The weekly menu — 28 slots, full recipes, macros, policy-validated. Consults household favourites before planning. Chat with the chef stays free-text. | `ExecutiveChefResult` (weekly-menu job only) |
| **Sous Chef** | Prep schedules and parallel cooking plans, each capped in minutes. Records exactly what each task will consume so inventory can deduct on completion. | `SousChefResult` |
| **Pantry Manager** | The pending shopping list — what's below threshold or short for the week, upserted so add-vs-append is never a choice. | `PantryManagerResult` |

All three get the identical MCP toolset — role boundaries are enforced by the prompt, not by hiding tools. Each run also gets a locally-built `get_job_context` tool: the authoritative source for date math and the *intent* behind a scheduled run.

### Scheduled jobs

Six cron jobs fire in-process (`agents/app/scheduler.py`). Times are in `KITCHEN_TIMEZONE` (default `Asia/Kolkata`). Every one is also a `POST /invoke/{job_name}` you can trigger from the **Automations** page to see its output immediately.

| Job | Role | Schedule | What it does |
|---|---|---|---|
| `weekly_menu` | Executive Chef | Sat 10:00 | Replace the saved menu with a fresh, complete Mon–Sun week; validate against household policy. |
| `sunday_prep` | Sous Chef | Sun 14:00 | One 60-minute batch-prep session for the week ahead. |
| `nightly_prep` | Sous Chef | daily 20:00 | A ≤10-minute task tonight so tomorrow's breakfast & lunch are quick. |
| `morning_cooking` | Sous Chef | Mon–Fri 06:30 | A parallel cooking plan for the breakfast & lunch being made now. |
| `dinner_cooking` | Sous Chef | Mon–Fri 18:00 | A parallel cooking plan for tonight's snack & dinner. |
| `pantry_manager` | Pantry Manager | daily 18:00 | Propose a shopping list for whatever's running low or needed for the week. |

If a job stops short of its required DB writes, `run_agent` sends corrective nudges and then **raises** — a job that saved 22 of 28 menu slots is recorded `failed` with the shortfall, never a blank `completed`. Telemetry for every run (success or failure) is posted to `dbmcp`.

---

## The UI

One React app, no router — `App.jsx` switch-renders each page from a single `/api/dashboard` payload, patched locally after each mutation.

- **Dashboard** — the week at a glance: today's meals, open tasks, low-stock count.
- **Weekly Menu** — every slot with ingredients and full recipe, rendered as lists.
- **Pantry** — read-only inventory with thresholds and last-updated.
- **Tasks** — prep schedules; checking one complete deducts its ingredients from inventory.
- **Chat** — talk to the Executive Chef; list and resume the 5 most recent conversations.
- **Automations** — every scheduled job, its recent runs, and a "run now" button per job.
- **Profile** — the single household record: name (drives the greeting), email (where notifications go), notification toggle, chef notes.

---

## Data model notes

`dbmcp/init_db.py` is one file that defines the schema + self-migration (idempotent `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ADD COLUMN` backfills on startup), the `@mcp.tool()` data operations, and the REST wrappers around them. `dbmcp/db_design.md` documents the same schema for humans; if the two disagree, `init_db.py` wins.

- **Inventory writes are propose-then-acknowledge.** The propose step never touches `inventory`; the acknowledge step is idempotent via a required `acknowledgement_key`. Replays return `{"replayed": true}` instead of double-counting.
- **There is no "shopping list" entity** — `shopping_items` *is* the one pending list, unique on `item_name`. `add_shopping_items` is an upsert; acknowledging a purchase adds the real quantity to `inventory` and deletes the row.
- **Prep deduction doesn't guard on stock** — a deduction always applies and can leave a visible negative balance until a shopping run. This is intentional.
- **The weekly menu is policy-checked** — `validate_weekly_menu_policy` encodes the household's rules (no egg/meat/fish in lunches, five distinct weekday lunches); the `weekly_menu` job builds the week slot-by-slot and fixes up any violations before finishing.

### Backups

```bash
python dbmcp/scripts/backup_db.py   # online-backup snapshot into dbmcp/backups/, keeps last 14
```

Safe under concurrent writers (SQLite online-backup API). Schedule it daily via cron / Task Scheduler.

---

## Running services standalone

Each service has its own `requirements.txt` / `package.json` and its own README with details.

```bash
# dbmcp — creates/migrates kitchen.db on startup, serves REST + MCP on :18000
cd dbmcp && pip install -r requirements.txt
KITCHENHQ_API_KEY=... python init_db.py

# agent-api — chat/invoke API + scheduler on :8090
cd agents && pip install -r requirements.txt
python -m uvicorn app.server:app --host 0.0.0.0 --port 8090
python cli.py    # or: interactive terminal REPL with the Executive Chef, no server

# chatui — Vite dev server + FastAPI backend
cd chatui && npm install && npm run dev
npm run build && python -m uvicorn app:app --port 8080
```

Tests (dbmcp only): `cd dbmcp && pip install -r requirements-dev.txt && pytest tests/` — each test spins up a temp SQLite DB, no live server needed. `chatui` and `agents` have no automated tests yet.

---

## Security & status

A `require_api_key` middleware sits in front of every route (except `/api/health`) on `dbmcp` and `chatui`, checking `X-API-Key` against `KITCHENHQ_API_KEY`. Because it's outer FastAPI middleware on `dbmcp`, it also covers the mounted MCP app at `/mcp` — no separate MCP-layer auth.

**This is prototype-grade.** One shared key for the whole household (not per-user accounts); SQLite with no replication (only local timestamped snapshots); no CI; linting/formatting not configured; `chatui` and `agents` have no tests. It runs a family kitchen well — it is not hardened for the open internet.

---

## Tech stack

**Backend:** Python 3, FastAPI, FastMCP / `mcp`, LangChain 1.x, `langchain-mcp-adapters`, `langchain-openai` / `langchain-ollama`, APScheduler, SQLite.
**Frontend:** React 18, Vite, `lucide-react`.
**Infra:** Docker Compose, pinned dependencies throughout.
