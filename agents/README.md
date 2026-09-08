# KitchenHQ Agent API

This is the agent-api service: a FastAPI app that talks to the KitchenHQ database through the MCP server, serves chat and on-demand job invocation for `chatui`, and runs the same jobs on an internal cron schedule. Every request/job builds its own LLM and MCP connections and disposes them before returning — nothing is kept open between calls (see `CLAUDE.md` for why that matters).

## Run with Docker

Copy `agents/.env.example` to `agents/.env`, set `OPENAI_API_KEY` and `KITCHENHQ_API_KEY` (must match the `dbmcp` service's key), then start the stack from the repository root:

```powershell
docker compose up --build
```

The API is available at `http://localhost:8090` (`/health`, `/chat`, `/jobs`, `/invoke/{job_name}`). `chatui` proxies to it for you, so day to day you shouldn't need to call it directly.

## Run the agent locally

Start the existing `dbmcp` container, set `MCP_URL=http://localhost:18000/mcp` and `KITCHENHQ_API_KEY`, install `agents/requirements.txt`, then either:

```powershell
python -m uvicorn app.server:app --host 0.0.0.0 --port 8090   # chat/invoke API + cron scheduler
```

or, for a quick terminal chat with no server/scheduler involved:

```powershell
python cli.py
```

Set `LLM_PROVIDER=ollama` and `OLLAMA_BASE_URL` to use Ollama instead of OpenAI.

## Email notifications

`app/email/` owns outbound mail (moved here from dbmcp — the agent is the only
process that sends it). One responsibility per module: `schemas` (payload contracts),
`smtp` (transport + recipient resolution), `render` (subject + text + HTML bodies),
`backfill` (fetch the saved menu / shopping items from dbmcp REST), `tools`
(`make_email_tools(settings)`, wired into every run by `kitchen_agent.run_agent` next
to `get_job_context`).

The three tools — `send_prep_task_email`, `send_weekly_plan_email`,
`send_shopping_list_email` — send one multipart (plain-text + HTML) message to the
household Profile address. Config is env-only: `SMTP_HOST`, `SMTP_PORT` (default 587,
465 with `SMTP_SSL=true`), `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_SSL`,
`SMTP_STARTTLS` (default true unless SSL), `SMTP_TIMEOUT`. With `SMTP_HOST` unset the
tools return `{"sent": false, "skipped": ...}` and jobs are unaffected;
`notify_on_task_creation = 0` on the profile suppresses all three. The recipient and
the saved-menu / shopping-list back-fill are fetched from dbmcp over `DB_API_URL`.
