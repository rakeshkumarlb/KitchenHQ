# KitchenHQ database schema

Use this schema when answering questions about KitchenHQ. Query the relevant table before making claims about stored data.

This file documents the schema created by `dbmcp/schema.sql` (run by
`kitchendb/schema.py`'s `initialize_database()`), which is the source of truth — if the
two ever disagree, trust `schema.sql`. The database is assumed to start empty or
already on this schema; there is no in-place migration of older layouts.

### Where the code lives (`dbmcp/`)

| Path | Holds |
|---|---|
| `constants.py` | Day / meal-type vocabulary + ordering. Vendored copy of `shared/constants.py` (kept in sync by `shared/sync.py`; a test guards drift). Also served to clients in the `constants` block of `GET /api/dashboard`. |
| `schema.sql` | The fresh-start DDL (all tables + indexes). |
| `kitchendb/config.py` | Env config: DB path, MCP allowed hosts, API key header. |
| `kitchendb/db.py` | `connect()` + row-fetch helpers. |
| `kitchendb/schema.py` | Runs `schema.sql`, then seeds a fresh DB. |
| `kitchendb/seed.py` | First-run seed data (inventory, 28 menu slots, prep tasks, profile). |
| `kitchendb/validation.py` | Pure input validation / normalization (no DB). |
| `kitchendb/models.py` | Pydantic request models. |
| `kitchendb/tools/` | Data operations by domain — each an MCP tool and/or a REST handler. |
| `kitchendb/routes.py` | The `/api/*` REST surface. |
| `kitchendb/server.py` | `create_app()` — the FastAPI app + mounted MCP app. |
| `init_db.py` | Thin compatibility shim (`uvicorn init_db:app`, the `python init_db.py` runner). |

## Tables

### `inventory`
Tracks available ingredients and stock thresholds.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Ingredient identifier |
| `item_name` | TEXT UNIQUE (case-insensitive) | Ingredient name |
| `category` | TEXT | Ingredient category |
| `quantity` | REAL | Quantity currently available. **May be negative** - prep acknowledgements deduct what a recipe used even when tracked stock was already at/near zero, so a shortfall stays visible until a shopping run tops it back up. |
| `unit` | TEXT | Unit of measurement |
| `minimum_threshold` | REAL (>= 0) | Reorder threshold |
| `last_updated` | DATETIME DEFAULT CURRENT_TIMESTAMP | Last stock update |

`quantity` has no `>= 0` CHECK — prep acknowledgements deduct what a recipe used even when tracked stock is already at/near zero.

### `wastage_log`
Records discarded ingredients.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Wastage record identifier |
| `item_name` | TEXT | Discarded ingredient (includes the discard reason) |
| `quantity_wasted` | REAL (> 0) | Amount discarded |
| `date_logged` | DATETIME DEFAULT CURRENT_TIMESTAMP | Time recorded |

### `weekly_menu`
Stores planned meals for each day of the week.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Menu item identifier |
| `day_of_week` | TEXT | Planned day (full lowercase weekday name) |
| `meal_type` | TEXT | Meal category — exactly one of `breakfast`, `lunch`, `snack`, `dinner` |
| `dish_name` | TEXT | Dish name |
| `is_kid_friendly` | BOOLEAN | Whether the dish is kid-friendly |
| `macros` | TEXT | Macronutrient information |
| `ingredients` | TEXT | JSON array of ingredient strings (plain text, one per entry). |
| `full_recipe` | TEXT DEFAULT '' | JSON array of method-step strings (plain text, one per entry). |
| `kid_rating` | INTEGER (1-5) | Child rating |
| `human_feedback` | TEXT | Additional feedback |
| `updated_at` | DATETIME DEFAULT CURRENT_TIMESTAMP | When the slot was last (re)planned — refreshed on every `add_weekly_menu_item` upsert (both INSERT and ON CONFLICT UPDATE). |

One row per `(day_of_week, meal_type)`, enforced by a `UNIQUE` index (`idx_weekly_menu_day_meal`). `add_weekly_menu_item(… ingredients: list[str], full_recipe: list[str] = [])` is a true atomic upsert (`INSERT … ON CONFLICT(day_of_week, meal_type) DO UPDATE`); day/meal are normalized (`.strip().lower()`) and validated against a fixed vocabulary (`constants.DAY_SET`, `constants.MEAL_TYPE_SET`), and both list args are trimmed and capped (`validation.MENU_LINES_LIMIT`, 40) then stored as JSON. The table holds at most 7 × 4 = 28 rows and two `weekly_menu` runs racing can't double-insert. The weekly plan is built slot-by-slot with `add_weekly_menu_item` and then checked with `validate_weekly_menu_policy` (no args, validates the saved table).

### `detailed_prep_schedule`
Defines food-preparation tasks for a human to execute.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Schedule identifier |
| `trigger_day` | TEXT | Day on which the task runs |
| `trigger_time` | TEXT | Time at which the task runs |
| `task_type` | TEXT | Task category |
| `detailed_instructions` | TEXT | JSON array of plain-text instruction step strings, e.g. `["Dice the onions.", "Heat oil..."]` (same convention as `weekly_menu.full_recipe`) |
| `ingredients_used` | TEXT DEFAULT '[]' | JSON array of `{item_name, quantity, unit}` objects - everything this task will consume, keyed by `inventory.item_name` (case-insensitive), set at creation and deducted when the task is checked complete |
| `is_completed` | BOOLEAN DEFAULT 0 | Completion status |
| `human_notes` | TEXT | Notes about the task |
| `status` | TEXT DEFAULT 'proposed' | `proposed` \| `acknowledged` \| `completed` \| `cancelled` |
| `acknowledgement_key` | TEXT | Idempotency key set when ingredients were deducted (`prep-<id>-complete`) |

`add_detailed_prep_schedule(detailed_instructions, ingredients_used)` validates and stores both JSON fields in one call - this is the only place that supplies what a task will consume; there is no separate acknowledge-time step to add it. `capture_prep_completion_status(is_completed=True)` finalizes a task: if `ingredients_used` is non-empty it looks up each `item_name` in `inventory` (case-insensitive), deducts `quantity` from every match, writes one `inventory_transactions` row per match (key `prep-<id>-complete:<index>`), and sets `status='acknowledged'`; otherwise it just sets `status='completed'`. Only an `acknowledged` task is locked against reopening (a `completed` task with nothing to deduct can still be unchecked). The deduction is **never blocked by low stock** - present ingredients are deducted (balance allowed to go negative) and an `item_name` with no matching `inventory` row is skipped, so acknowledging always succeeds. `add_detailed_prep_schedule` only writes the row — any email is sent separately by the agent via `send_prep_task_email` (see Notifications below). `cancel_prep_schedule` soft-cancels a not-yet-acknowledged task (`status='cancelled'`); cancelled tasks are excluded from `get_prep_schedules` and the dashboard, which also caps returned completed tasks at the 10 most recent.

### `inventory_transactions`
Immutable ledger of every inventory quantity change made through acknowledgement flows.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Transaction identifier |
| `inventory_id` | INTEGER REFERENCES inventory(id) | Affected ingredient |
| `quantity_change` | REAL (<> 0) | Signed change applied |
| `quantity_before` | REAL | Quantity before the change |
| `quantity_after` | REAL | Quantity after the change (may be negative - there is no `>= 0` CHECK, matching `inventory.quantity`) |
| `reason` | TEXT | Why the change happened |
| `source_type` | TEXT | `prep_schedule` \| `shopping_item` |
| `source_id` | INTEGER | Id of the source record |
| `idempotency_key` | TEXT UNIQUE | `{acknowledgement_key}:{index}`, prevents double-applying a replayed acknowledgement |
| `created_at` | DATETIME DEFAULT CURRENT_TIMESTAMP | When recorded |

`GET /api/dashboard` derives a `consumption` array from this ledger: for every negative `quantity_change` in the last 7 days it returns `{inventory_id, item_name, unit, quantity_consumed, transaction_count, last_consumed_at}` per ingredient, ordered by `quantity_consumed` descending. (Only acknowledged prep deductions land here today, so it reads as "ingredients used by prep this week".)

`GET /api/dashboard` also returns a `constants` block — `{days, meal_types, day_order, meal_type_order}` from `constants.py` — so non-Python clients (chatui) don't hard-code the weekday/meal vocabulary.

### `shopping_items`
There is no separate "list" entity — this table IS the one pending shopping list. Every
row is something still waiting to be bought; a purchase deletes its row rather than
flipping a status.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Item identifier |
| `item_name` | TEXT UNIQUE COLLATE NOCASE | Ingredient name - unique case-insensitively, which is what makes `add_shopping_items` a true upsert |
| `proposed_quantity` | REAL (> 0) | Quantity proposed |
| `unit` | TEXT | Unit of measurement |
| `created_at` | DATETIME DEFAULT CURRENT_TIMESTAMP | When first proposed |
| `updated_at` | DATETIME DEFAULT CURRENT_TIMESTAMP | Last time the quantity/unit changed |

`add_shopping_items(items)` is an `INSERT … ON CONFLICT(item_name) DO UPDATE` upsert: an item with a name already pending has its `proposed_quantity` increased by the new amount (and `unit` overwritten) instead of creating a duplicate row, so a caller never has to check for an existing list before deciding whether to create or append — the ambiguity is resolved in this one method, not left to whoever calls it. `edit_shopping_item`/`delete_shopping_item` correct or drop one row; `clear_shopping_items` empties the whole table. None of these touch `inventory`.

### `agent_runs`
Best-effort telemetry for agent jobs, both scheduled and on-demand (`agents/app/jobs.py`, run by the `agent-api` service).

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Run identifier |
| `agent_role` | TEXT | `executive_chef` \| `sous_chef` \| `pantry_manager` |
| `job_name` | TEXT | Scheduled job name, e.g. `weekly_menu` |
| `status` | TEXT | `completed` \| `failed` |
| `result` | TEXT | Result summary |
| `error` | TEXT | Error detail, if failed |
| `started_at` | DATETIME DEFAULT CURRENT_TIMESTAMP | Start time |
| `finished_at` | DATETIME DEFAULT CURRENT_TIMESTAMP | End time |

### `chat_sessions`
Durable storage for the Executive Chef chat transcript per browser/session, so restarts and multiple `chatui` instances don't lose conversation history.

| Column | Type | Description |
|---|---|---|
| `session_id` | TEXT PRIMARY KEY | Client-generated session id |
| `messages_json` | TEXT DEFAULT '[]' | LangChain messages, serialized with `langchain_core.messages.messages_to_dict` |
| `updated_at` | DATETIME DEFAULT CURRENT_TIMESTAMP | Last write |

`GET /api/chat-sessions?limit=5` lists the most recently updated sessions (session_id, updated_at, and a preview built from the first human message) so `chatui` can offer "recent conversations" without loading full transcripts. Rows are never pruned by this endpoint — it only limits what's returned.

### `user_profile`
A single household profile row (`id` is pinned to `1`), seeded with `name = 'Alex Kim'` on first startup.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY CHECK (id = 1) | Always `1` |
| `name` | TEXT DEFAULT '' | Household name, shown in the chatui header/greeting |
| `email` | TEXT DEFAULT '' | Where prep-task alert emails are sent |
| `cc_emails` | TEXT DEFAULT '' | Extra addresses (comma/semicolon/newline separated) cc'd on every task-alert email |
| `notes` | TEXT DEFAULT '' | Free-text "note for the chef" — surfaced to the Executive Chef as weekly-menu planning context |
| `favorite_recipes` | TEXT DEFAULT '[]' | JSON array (max 10, newest first) of `{dish_name, rating, rated_at}`, maintained automatically from weekly-menu ratings — not user-patchable |
| `notify_on_task_creation` | INTEGER DEFAULT 1 | Global email switch: `1` = the `send_*_email` tools deliver, `0` = they all return `{"sent": false}` |
| `updated_at` | DATETIME DEFAULT CURRENT_TIMESTAMP | Last write |

`GET /api/profile` returns the row; `PUT /api/profile` patches only the fields supplied (`name`, `email`, `cc_emails`, `notes`, `notify_on_task_creation`; a non-`@` `email` is rejected 400). The row is also embedded in `GET /api/dashboard` as `profile`.

`favorite_recipes` is rewritten inside `capture_weekly_menu_rating` (`POST /api/weekly-menu/{id}/rating`): a 4- or 5-star rating moves that dish to the front (newest first, deduped case-insensitively), any lower rating removes it, and the list is trimmed to 10 — so an older favourite falls off once ten fresher dishes have been top-rated. The `get_household_preferences` MCP tool returns `{chef_note, favorite_recipes, has_preferences, guidance}` for agents (the Executive Chef consults it before planning a week); `has_preferences` is `false` and `guidance` says "optional context, not a blocker" when both the note and the favourites list are empty, so a fresh install doesn't stall the weekly-menu job.

## Notifications

Email notifications are **no longer part of dbmcp**. They moved to
`agents/app/email/` (the agent is the only process that sends mail):
the three `send_*_email` tools are built locally per agent run, SMTP config lives on
the `agent-api` service, and the two bits of stored data an email needs (the recipient
`user_profile` row, and the saved `weekly_menu` / `shopping_items` used to back-fill an
omitted payload) are fetched over this service's REST API (`GET /api/profile`,
`GET /api/dashboard`). dbmcp keeps no SMTP settings and has no `/api/notifications/*`
routes. `user_profile.notify_on_task_creation` is still the household's global email
on/off switch, read by the agent over `GET /api/profile`.

## Idempotency pattern

`detailed_prep_schedule` and `shopping_items` both follow propose-then-acknowledge:
proposing (`add_detailed_prep_schedule`, `add_shopping_items`) never touches `inventory`,
and acknowledging requires a caller-supplied `acknowledgement_key`. For prep, the key is
persisted on the still-present `detailed_prep_schedule` row (`status='acknowledged'`
short-circuits a replay). Shopping items are instead *deleted* the moment they're
acknowledged (that's what "clears" them off the list), so there's no row left to check a
key against on replay — instead, each deduction's `inventory_transactions.idempotency_key`
(`{acknowledgement_key}:{shopping_item_id}`) is checked directly before applying it, and a
match is treated as an already-applied replay. Either way, a replay returns
`{"replayed": true}` instead of double-applying. Preserve this pattern when adding new
inventory-affecting flows.
