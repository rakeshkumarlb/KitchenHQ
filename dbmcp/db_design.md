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
| `kitchendb/seed.py` | First-run seed data (inventory, 28 menu slots, prep tasks, profile, household members). |
| `kitchendb/validation.py` | Pure input validation / normalization (no DB). |
| `kitchendb/embeddings.py` | Local embedding model (`fastembed`) + numpy cosine similarity — the semantic half of recipe search. |
| `kitchendb/keyword_search.py` | SQLite FTS5 query + BM25 normalization — the keyword half of recipe search. |
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
| `quantity` | REAL | Quantity currently available, **in `unit`**. **May be negative** - prep acknowledgements deduct what a recipe used even when tracked stock was already at/near zero, so a shortfall stays visible until a shopping run tops it back up. |
| `unit` | TEXT | Canonical stock unit — one of `g`, `kg`, `ml`, `l`, `pcs`. `add_inventory` rejects anything else (accepting aliases like `grams`/`litre`/`pieces` and storing the short form). Every deduction/intake converts its own quantity into this unit before touching `quantity` (see **Units of measure** below). |
| `minimum_threshold` | REAL (>= 0) | Reorder threshold |
| `last_updated` | DATETIME DEFAULT CURRENT_TIMESTAMP | Last stock update |

`quantity` has no `>= 0` CHECK — prep acknowledgements deduct what a recipe used even when tracked stock is already at/near zero.

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
| `score` | INTEGER (0-100) | Food Inspector's audit score for this slot's dish, or `NULL` if not yet audited |
| `audit_feedback` | TEXT | Food Inspector's written explanation of `score` |
| `updated_at` | DATETIME DEFAULT CURRENT_TIMESTAMP | When the slot was last (re)planned — refreshed on every `add_weekly_menu_item` upsert (both INSERT and ON CONFLICT UPDATE). |

One row per `(day_of_week, meal_type)`, enforced by a `UNIQUE` index (`idx_weekly_menu_day_meal`). `add_weekly_menu_item(… ingredients: list[str], full_recipe: list[str] = [])` is a true atomic upsert (`INSERT … ON CONFLICT(day_of_week, meal_type) DO UPDATE`); day/meal are normalized (`.strip().lower()`) and validated against a fixed vocabulary (`constants.DAY_SET`, `constants.MEAL_TYPE_SET`), and both list args are trimmed and capped (`validation.MENU_LINES_LIMIT`, 40) then stored as JSON. Every upsert also resets `score`/`audit_feedback` to `NULL`, since a re-planned slot is a new decision awaiting judgement. The table holds at most 7 × 4 = 28 rows and two `weekly_menu` runs racing can't double-insert. The weekly plan is built slot-by-slot with `add_weekly_menu_item` and then checked with `validate_weekly_menu_policy` (no args, validates the saved table). See **Food Inspector / auditing** below for how `score`/`audit_feedback` get filled in.

### `detailed_prep_schedule`
Defines food-preparation tasks for a human to execute.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Schedule identifier |
| `trigger_day` | TEXT | Day on which the task runs |
| `trigger_time` | TEXT | Time at which the task runs |
| `task_type` | TEXT | Task category |
| `detailed_instructions` | TEXT | JSON array of plain-text instruction step strings, e.g. `["Dice the onions.", "Heat oil..."]` (same convention as `weekly_menu.full_recipe`) |
| `ingredients_used` | TEXT DEFAULT '[]' | JSON array of `{item_name, quantity, unit}` objects - everything this task will consume, keyed by `inventory.item_name` (case-insensitive), set at creation and deducted when the task is checked complete. `unit` may be g/kg/ml/l/pcs or a culinary unit (tsp/tbsp/cup, approximated to g/ml on deduction); each `quantity` is converted into the matched row's stored unit first. A line whose unit can't be reconciled with the row's (different dimension, or unrecognized) is skipped and surfaced in the completion response's `conversion_warnings`, not applied. |
| `is_completed` | BOOLEAN DEFAULT 0 | Completion status |
| `human_notes` | TEXT | Notes about the task |
| `status` | TEXT DEFAULT 'assigned' | `assigned` \| `acknowledged` \| `completed` \| `cancelled` \| `expired` |
| `acknowledgement_key` | TEXT | Idempotency key set when ingredients were deducted (`prep-<id>-complete`) |
| `score` | INTEGER (0-100) | Food Inspector's audit score for this task, or `NULL` if not yet audited |
| `audit_feedback` | TEXT | Food Inspector's written explanation of `score` |
| `created_at` | DATETIME DEFAULT CURRENT_TIMESTAMP | When the task was assigned - the clock `expire_stale_prep_tasks` measures its 2-hour window against |

`add_detailed_prep_schedule(detailed_instructions, ingredients_used)` validates and stores both JSON fields in one call - this is the only place that supplies what a task will consume; there is no separate acknowledge-time step to add it. `capture_prep_completion_status(is_completed=True)` is the single human action that finalizes a task ("check this off") - there is no distinct "acknowledge" step after it. `completed` and `acknowledged` are not two stages of that action; they're its two possible outcomes, decided purely by whether `ingredients_used` was non-empty at creation: if non-empty, the call looks up each `item_name` in `inventory` (case-insensitive), deducts `quantity` from every match, writes one `inventory_transactions` row per match (key `prep-<id>-complete:<index>`), and sets `status='acknowledged'`; if empty, it just sets `status='completed'` with nothing to deduct. Both statuses mean the same thing to the household ("done") and are treated identically everywhere they're read (`get_prep_schedules`, the dashboard, chatui's Task List all just check `is_completed`); the one place the distinction matters is reopening - only an `acknowledged` task is locked against a later `is_completed=False` call (since undoing a real deduction isn't safe to automate), while a `completed` task with nothing to deduct can still be unchecked. Each `quantity` is converted into the matched row's stored unit before it's deducted (`kitchendb.units.convert` — see **Units of measure**); a line whose unit can't be reconciled with the row's is skipped and listed in the response's `conversion_warnings`. The deduction is **never blocked by low stock** - present ingredients are deducted (balance allowed to go negative) and an `item_name` with no matching `inventory` row is skipped, so acknowledging always succeeds. `add_detailed_prep_schedule` only writes the row — any email is sent separately by the agent via `send_prep_task_email` (see Notifications below). `cancel_prep_schedule` soft-cancels a not-yet-acknowledged, not-yet-expired task (`status='cancelled'`); cancelled tasks are excluded from `get_prep_schedules` and the dashboard, which also caps returned completed tasks at the 10 most recent.

`expire_stale_prep_tasks()` (an MCP tool, no REST route - only the `expire_prep_tasks` scheduled job calls it) marks every task still `status='assigned'` more than 2 hours past `created_at` as `status='expired'`; expiring never touches inventory (same as cancellation) and is idempotent - already-`completed`/`acknowledged`/`cancelled`/`expired` rows are left alone. An `expired` task can no longer be acknowledged or cancelled (both reject with a 400), the same way an `acknowledged` one can't be reopened or cancelled.

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
| `proposed_quantity` | REAL (> 0) | Quantity proposed, in `unit` |
| `unit` | TEXT | Unit of measurement. `add_shopping_items`/`edit_shopping_item` tidy a recognized alias to its canonical `g`/`kg`/`ml`/`l`/`pcs` form but stay permissive on anything else (this list is a human scratchpad); the reconciliation that matters happens at acknowledge time. |
| `created_at` | DATETIME DEFAULT CURRENT_TIMESTAMP | When first proposed |
| `updated_at` | DATETIME DEFAULT CURRENT_TIMESTAMP | Last time the quantity/unit changed |

`add_shopping_items(items)` is an `INSERT … ON CONFLICT(item_name) DO UPDATE` upsert: an item with a name already pending has its `proposed_quantity` increased by the new amount (and `unit` overwritten) instead of creating a duplicate row, so a caller never has to check for an existing list before deciding whether to create or append — the ambiguity is resolved in this one method, not left to whoever calls it. `edit_shopping_item`/`delete_shopping_item` correct or drop one row; `clear_shopping_items` empties the whole table. None of these touch `inventory`.

### `agent_runs`
Best-effort telemetry for agent jobs, both scheduled and on-demand (`agents/app/jobs.py`, run by the `agent-api` service).

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Run identifier |
| `agent_role` | TEXT | `executive_chef` \| `sous_chef` \| `pantry_manager` \| `food_inspector` |
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
| `favorite_recipes` | TEXT DEFAULT '[]' | JSON array (max 10, newest first) of `{dish_name, rating, rated_at}` — not user-patchable. Legacy field: nothing currently writes to it (the weekly-menu star-rating flow that used to populate it was removed in favour of `household_members`), but it is still read and returned as-is. |
| `notify_on_task_creation` | INTEGER DEFAULT 1 | Global email switch: `1` = the `send_*_email` tools deliver, `0` = they all return `{"sent": false}` |
| `updated_at` | DATETIME DEFAULT CURRENT_TIMESTAMP | Last write |

`GET /api/profile` returns the row; `PUT /api/profile` patches only the fields supplied (`name`, `email`, `cc_emails`, `notes`, `notify_on_task_creation`; a non-`@` `email` is rejected 400). The row is also embedded in `GET /api/dashboard` as `profile`.

The `get_household_preferences` MCP tool returns `{chef_note, favorite_recipes, household_members, has_preferences, guidance}` for agents — the single shared source of household rules/preferences consulted by every cooking-decision role (Executive Chef and Sous Chef before deciding what to cook, Food Inspector when auditing what they decided); `has_preferences` is `false` and `guidance` says "optional context, not a blocker" when the note, favourites, and household members are all empty, so a fresh install doesn't stall the weekly-menu job.

### `household_members`
Individual household members, each with their own dietary preferences and health conditions — consulted alongside the chef note/favourites when picking recipes, and fed to the Food Inspector as the same context the cooking roles used.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Member identifier |
| `name` | TEXT | Member's name |
| `dietary_preferences` | TEXT DEFAULT '[]' | JSON array of short plain-text strings, e.g. `["vegetarian", "no nuts"]` |
| `health_conditions` | TEXT DEFAULT '[]' | JSON array of short plain-text strings, e.g. `["diabetic", "lactose intolerant"]` |
| `updated_at` | DATETIME DEFAULT CURRENT_TIMESTAMP | Last write |

`add_household_member`/`update_household_member`/`delete_household_member`/`list_household_members` are REST-only (`/api/household-members`, human-edited on the Profile page, not agent tools). The row is also embedded in `GET /api/dashboard` as `household_members` and folded into `get_household_preferences`.

### `recipes`
The household recipe catalog. Each row is one recipe, searchable by a hybrid of keyword and semantic matching.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Recipe identifier |
| `name` | TEXT | Recipe name (denormalized copy of `recipe.name`, for fast alphabetical listing) |
| `recipe` | TEXT | Full structured recipe as JSON: `name`, `origin`, `serves`, `prep_time_minutes`, `cook_time_minutes`, `ingredients` (list of `{item_name, quantity, unit}`, same shape as `detailed_prep_schedule.ingredients_used`), `instructions` (list of plain-text step strings, same convention as `weekly_menu.full_recipe`), `macros_per_serving` (`{calories, protein_g, carbs_g, fat_g, fiber_g}`), `meal_types` (validated against `constants.MEAL_TYPE_SET`), `tags`, `source`. There is no separate `dietary_flags` field — diet category, allergen/restriction and nutrition labels all live in `tags`, per the household's recipe catalog standards (`agents/prompts/system.md`) that both the Executive Chef (writing tags) and the Food Inspector (auditing them) follow. |
| `embedding` | TEXT | JSON array of floats — the recipe's semantic-search vector, built once from its whole text (name + origin + ingredients + instructions + tags, no chunking) by `kitchendb/embeddings.py`. Always recomputed alongside `recipe` by `add_recipe`/`update_recipe`, so it never drifts out of sync with the content it represents. |
| `rating` | INTEGER (1-5, nullable) | Household preference signal, separate from recipe content — set via `rate_recipe`, never touches `embedding` |
| `score` | INTEGER (0-100, nullable) | Food Inspector's judgement of this recipe's tags/instructions; `NULL` means not yet audited |
| `audit_feedback` | TEXT (nullable) | Food Inspector's written feedback alongside `score` |
| `created_at` | DATETIME DEFAULT CURRENT_TIMESTAMP | When added |
| `updated_at` | DATETIME DEFAULT CURRENT_TIMESTAMP | Last edit |

No uniqueness constraint on `name` — a household may keep more than one version of the same dish. `add_recipe`/`update_recipe` reuse existing validation: `normalize_ingredients_used` (`validation.py`) for `ingredients`, `clean_line_list` for `instructions`/`tags`, `validate_meal_type` for `meal_types`. `update_recipe` resets `score`/`audit_feedback` to `NULL` on every edit — a changed recipe is a new decision awaiting judgement, same convention as `add_weekly_menu_item`. `get_unaudited_recipes`/`record_recipe_audit` (`kitchendb/tools/audit.py`, MCP-only) are the Food Inspector's third audit pair alongside the `weekly_menu` and `detailed_prep_schedule` ones.

### `recipes_fts`
A standalone (not `content=`-linked) SQLite FTS5 virtual table — `name`, `ingredients`, `tags`, `instructions` columns, rowid always equal to the matching `recipes.id`. Kept in sync explicitly by `add_recipe`/`update_recipe`/`delete_recipe`/`reindex_recipes` (no SQL triggers — every other derived column in this schema, e.g. `recipes.embedding`, is synced the same explicit way from Python). This is the keyword half of `search_recipes`; there is no REST/MCP surface of its own.

`search_recipes(query, top_k=10)` combines two independent signals per candidate recipe: a semantic score (query embedded with the same local model, ranked against every row by cosine similarity — `kitchendb/embeddings.cosine_top_k`) and a keyword score (`recipes_fts` queried via FTS5 `MATCH`, BM25 output min-max normalized to `[0, 1]` across the matching rows — `kitchendb/keyword_search.keyword_top_k`). A recipe is only returned if its keyword score **or** its semantic score exceeds `0.65` (`kitchendb.tools.recipes._MATCH_THRESHOLD`); qualifying recipes are ranked by the higher of the two scores. Both are a full re-scan per call, no persistent in-memory index to invalidate; correct and fast enough at catalog scale (tens–hundreds of rows). A query that clears the bar for fewer than `top_k` recipes — including zero — returns exactly that many; results are never padded with weak matches. `reindex_recipes()` (MCP-only, no REST route, same pattern as `expire_stale_prep_tasks`) re-embeds and re-indexes every row — for bulk backfill or an embedding-model upgrade, not the normal write path.

Executive Chef and Sous Chef call `search_recipes` before writing new dish instructions (in chat, the `weekly_menu` job, and prep jobs) and adapt what's found via `get_household_preferences`, rather than inventing from scratch — soft prompt guidance, not a `JOB_REQUIRED_TOOLS` gate. Executive Chef also owns recipe CRUD from chat, including transcribing a household member's pasted recipe text into this structured shape via `add_recipe`.

## Food Inspector / auditing

The Food Inspector is an LLM-as-judge role: it evaluates weekly-menu slots and prep tasks that the Executive Chef / Sous Chef already saved, scoring each against the exact same rules those roles used (`system.md`'s dietary/macro rules plus `get_household_preferences`) — no separate rules file, so the judge and the judged always see the same context. It never edits menu/task content, only records a verdict via two tools:

- `get_unaudited_weekly_menu_items()` / `record_weekly_menu_audit(weekly_menu_id, score, audit_feedback)` — operate on `weekly_menu` rows where `score IS NULL`.
- `get_unaudited_prep_tasks()` / `record_prep_task_audit(prep_schedule_id, score, audit_feedback)` — operate on `detailed_prep_schedule` rows where `score IS NULL`, **including cancelled tasks** (the decision being judged is what the Sous Chef planned, not whether it was later performed — contrast with `get_prep_schedules`, which excludes cancelled rows).

Both run as nightly scheduled jobs (`menu_audit`, `task_audit` in `agents/app/jobs.py`), also invocable on demand from chatui's Automations page like any other job. `score`/`audit_feedback` ride along in `GET /api/dashboard`'s `menu`/`tasks` arrays; a `NULL` score means "not yet audited."

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
persisted on the still-present `detailed_prep_schedule` row - `status='acknowledged'`
short-circuits a replay of `capture_prep_completion_status(is_completed=True)`, which
just returns the row unchanged (no `replayed` flag; check `status` instead). Shopping
items are instead *deleted* the moment they're acknowledged (that's what "clears" them
off the list), so there's no row left to check a key against on replay — instead, each
deduction's `inventory_transactions.idempotency_key`
(`{acknowledgement_key}:{shopping_item_id}`) is checked directly before applying it, a
match is treated as an already-applied replay, and `acknowledge_shopping_items` *does*
report that back as `{"replayed": true, ...}` in its response (prep has no equivalent
flag - its idempotency is silent). Both paths are idempotent either way; only the
response shape differs. Preserve idempotency (not the exact response shape) when adding
new inventory-affecting flows.

## Units of measure

`dbmcp/kitchendb/units.py` is the single place inventory math reconciles units. Every
inventory row is stored in one of five canonical units — `g`, `kg` (base gram), `ml`,
`l` (base millilitre), `pcs` (base piece) — and `add_inventory` enforces that (aliases
such as `grams`, `kilograms`, `litre`, `pieces` are accepted and stored in the short
form; anything else is a 400). The seed data (`kitchendb/seed.py`) uses only canonical
units; there is no migration of older layouts (a database starts empty or already on
this schema).

`convert(quantity, from_unit, to_unit) -> (value, note, ok)`:

- blank `from_unit`, or `from_unit == to_unit` → passthrough (`ok=True`, `note=""`).
- same dimension → `quantity * from_base / to_base`, rounded to 4 dp (`500 g` into a `kg`
  row → `0.5`; `2 kg` into a `g` row → `2000`). `note` reads `converted 500 g -> 0.5 kg`
  and is appended to the `inventory_transactions.reason`.
- culinary units `tsp`/`tbsp`/`cup`/`pinch`/`dash`/`handful` (plus `oz`/`lb`/`fl oz`/
  `pint`/`quart`/`gallon`) are approximated to a gram-or-millilitre magnitude
  (`tsp`=5, `tbsp`=15, `cup`=240, assuming density ≈ water) and adopt the target row's
  dimension.
- different dimensions, or an unrecognized unit on either side → `ok=False`; the caller
  (`capture_prep_completion_status`, `acknowledge_shopping_items`) **skips that line**,
  leaves the balance / shopping row untouched, and returns the reason in
  `conversion_warnings` (prep) or `warnings` (shopping). Acknowledging still succeeds
  overall.

`adjust_inventory_quantity` and `remove_or_discard_inventory` are manual corrections that
operate directly in the row's own unit and do no conversion.
