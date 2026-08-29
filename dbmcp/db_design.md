# KitchenHQ database schema

Use this schema when answering questions about KitchenHQ. Query the relevant table before making claims about stored data.

This file is generated to match `dbmcp/init_db.py`'s `initialize_database()`, which is the source of truth — if the two ever disagree, trust the code.

## Tables

### `inventory`
Tracks available ingredients and stock thresholds.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Ingredient identifier |
| `item_name` | TEXT UNIQUE (case-insensitive) | Ingredient name |
| `category` | TEXT | Ingredient category |
| `quantity` | REAL (>= 0) | Quantity currently available |
| `unit` | TEXT | Unit of measurement |
| `minimum_threshold` | REAL (>= 0) | Reorder threshold |
| `last_updated` | DATETIME DEFAULT CURRENT_TIMESTAMP | Last stock update |

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
| `meal_type` | TEXT | Meal category, such as breakfast or dinner |
| `dish_name` | TEXT | Dish name |
| `is_kid_friendly` | BOOLEAN | Whether the dish is kid-friendly |
| `macros` | TEXT | Macronutrient information |
| `ingredients` | TEXT | Ingredients for the dish |
| `full_recipe` | TEXT DEFAULT '' | Full recipe text |
| `kid_rating` | INTEGER (1-5) | Child rating |
| `human_feedback` | TEXT | Additional feedback |

One row per `(day_of_week, meal_type)`; `add_weekly_menu_item` upserts on that pair.

### `detailed_prep_schedule`
Defines food-preparation tasks for a human to execute.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Schedule identifier |
| `trigger_day` | TEXT | Day on which the task runs |
| `trigger_time` | TEXT | Time at which the task runs |
| `task_type` | TEXT | Task category |
| `detailed_instructions` | TEXT | Preparation instructions |
| `is_completed` | BOOLEAN DEFAULT 0 | Completion status |
| `human_notes` | TEXT | Notes about the task |
| `ingredients_used` | TEXT | Ingredients consumed (free text, set at creation) |
| `ingredients_created` | TEXT | Ingredients produced (free text, set at creation) |
| `status` | TEXT DEFAULT 'proposed' | `proposed` \| `acknowledged` \| `completed` |
| `consumption_json` | TEXT DEFAULT '[]' | Explicit `{inventory_id, quantity, unit}` items deducted on acknowledgement |
| `acknowledgement_key` | TEXT | Idempotency key from `acknowledge_prep_schedule` |

### `inventory_transactions`
Immutable ledger of every inventory quantity change made through acknowledgement flows.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Transaction identifier |
| `inventory_id` | INTEGER REFERENCES inventory(id) | Affected ingredient |
| `quantity_change` | REAL (<> 0) | Signed change applied |
| `quantity_before` | REAL | Quantity before the change |
| `quantity_after` | REAL (>= 0) | Quantity after the change |
| `reason` | TEXT | Why the change happened |
| `source_type` | TEXT | `prep_schedule` \| `shopping_list` |
| `source_id` | INTEGER | Id of the source record |
| `idempotency_key` | TEXT UNIQUE | `{acknowledgement_key}:{index}`, prevents double-applying a replayed acknowledgement |
| `created_at` | DATETIME DEFAULT CURRENT_TIMESTAMP | When recorded |

### `shopping_lists`
A proposed (and later purchased) shopping run.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | List identifier |
| `status` | TEXT DEFAULT 'proposed' | `proposed` \| `purchased` |
| `generated_at` | DATETIME DEFAULT CURRENT_TIMESTAMP | When proposed |
| `acknowledged_at` | DATETIME | When purchases were acknowledged |
| `acknowledgement_key` | TEXT UNIQUE | Idempotency key from `acknowledge_shopping_list` |

### `shopping_items`
Line items belonging to a `shopping_lists` row.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Item identifier |
| `shopping_list_id` | INTEGER REFERENCES shopping_lists(id) | Parent list |
| `item_name` | TEXT | Ingredient name |
| `proposed_quantity` | REAL (> 0) | Quantity proposed |
| `actual_quantity` | REAL (>= 0) | Quantity actually purchased (set on acknowledgement) |
| `unit` | TEXT | Unit of measurement |
| `status` | TEXT DEFAULT 'proposed' | `proposed` \| `purchased` |

### `agent_runs`
Best-effort telemetry for scheduled agent jobs (`executivechef_agent/worker.py`).

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

## Idempotency pattern

`detailed_prep_schedule`/`inventory_transactions` and `shopping_lists`/`shopping_items` both follow propose-then-acknowledge: proposing never touches `inventory`, and acknowledging requires a caller-supplied `acknowledgement_key` that's persisted and checked before applying inventory changes, so replays return `{"replayed": true}` instead of double-applying. Preserve this pattern when adding new inventory-affecting flows.
