-- KitchenHQ database schema (fresh-start DDL).
--
-- This file is the source of truth for the schema; db_design.md documents the same
-- tables for humans. initialize_database() (kitchendb/schema.py) executes this on
-- every startup - every statement is idempotent (CREATE ... IF NOT EXISTS), so it is
-- safe to run against an already-initialized database. There is no in-place migration
-- of older layouts: a database is expected to be empty or already on this schema.

CREATE TABLE IF NOT EXISTS inventory (
    id INTEGER PRIMARY KEY,
    item_name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    category TEXT NOT NULL,
    quantity REAL NOT NULL,
    unit TEXT NOT NULL,
    minimum_threshold REAL NOT NULL DEFAULT 0 CHECK (minimum_threshold >= 0),
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
);
-- Note: quantity has no >= 0 CHECK. Prep acknowledgements deduct what a recipe used
-- even when tracked stock is already at/near zero, so a balance may go negative and
-- stay visible until a shopping run tops it back up.

CREATE TABLE IF NOT EXISTS weekly_menu (
    id INTEGER PRIMARY KEY,
    day_of_week TEXT NOT NULL,
    meal_type TEXT NOT NULL,
    dish_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    is_kid_friendly BOOLEAN NOT NULL,
    macros TEXT NOT NULL,
    ingredients TEXT NOT NULL,
    full_recipe TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    source_recipe_id INTEGER REFERENCES recipes(id),
    score INTEGER CHECK (score BETWEEN 0 AND 100),
    audit_feedback TEXT,
    is_skipped BOOLEAN NOT NULL DEFAULT 0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
-- Exactly one row per (day_of_week, meal_type); the unique index makes
-- add_weekly_menu_item a true atomic upsert. is_skipped marks a placeholder written by
-- mark_weekly_menu_skipped for a slot the household's skip_meals config excluded this
-- run, so a stale dish saved for that slot in an earlier week stops showing once it's
-- skipped - add_weekly_menu_item always clears is_skipped back to 0 when a real dish is
-- saved for the slot again. description is a short household-facing summary of the dish,
-- shown on the Weekly Menu page's meal card in place of a raw ingredient/macro preview.
-- tags is the same freeform taxonomy as recipes.tags (diet category, allergen/nutrition
-- labels, cuisine/method), shown in the meal's recipe modal the same way the catalog
-- shows a recipe's tags. source_recipe_id is a soft (unenforced) reference to the
-- recipes catalog row this slot's dish was adapted from via search_recipes, if any - NULL
-- when the dish was invented or transcribed fresh for this slot only. It is provenance,
-- not a foreign key relationship the app relies on: recorded so a later "recreate
-- instructions"/"identify tags" request for this slot knows which record is authoritative
-- (the linked catalog recipe when set, this row directly when NULL) - see
-- kitchendb/tools/weekly_menu.py::add_weekly_menu_item.
CREATE UNIQUE INDEX IF NOT EXISTS idx_weekly_menu_day_meal
    ON weekly_menu (day_of_week, meal_type);

CREATE TABLE IF NOT EXISTS weekly_plans (
    id INTEGER PRIMARY KEY,
    week_start_date TEXT NOT NULL,
    week_end_date TEXT NOT NULL,
    skip_meals_snapshot TEXT NOT NULL DEFAULT '{}',
    chef_note_snapshot TEXT NOT NULL DEFAULT '',
    restrictions_snapshot TEXT NOT NULL DEFAULT '[]',
    score INTEGER CHECK (score BETWEEN 0 AND 100),
    audit_feedback TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
-- One row per planned week (the weekly_menu job upserts it, keyed by week_start_date -
-- the Monday - on every run; a re-plan resets score/audit_feedback to NULL, same
-- convention as weekly_menu). skip_meals_snapshot/chef_note_snapshot/restrictions_snapshot
-- are copies of user_profile.skip_meals/notes/restrictions (restrictions filtered to
-- enabled: true) at the moment this week was planned - a record of what the Executive
-- Chef actually saw, since the live config can change afterward. This is a deliberate
-- exception to the rest of this schema's audits (weekly_menu, detailed_prep_schedule,
-- recipes still judge against the household's current rules): weekly_plan_audit judges
-- whole-week completeness against what was true at plan time, not what's true tonight.
-- score/audit_feedback are the Food Inspector's judgement of this week's whole-plan,
-- week-scope properties (e.g. lunch variety, slot completeness) that can't be judged from
-- a single weekly_menu row in isolation - see get_unaudited_weekly_plans/record_weekly_plan_audit.
CREATE UNIQUE INDEX IF NOT EXISTS idx_weekly_plans_start
    ON weekly_plans (week_start_date);

CREATE TABLE IF NOT EXISTS detailed_prep_schedule (
    id INTEGER PRIMARY KEY,
    trigger_day TEXT NOT NULL,
    trigger_time TEXT NOT NULL,
    task_type TEXT NOT NULL,
    detailed_instructions TEXT NOT NULL,
    ingredients_used TEXT NOT NULL DEFAULT '[]',
    is_completed BOOLEAN NOT NULL DEFAULT 0,
    human_notes TEXT,
    status TEXT NOT NULL DEFAULT 'assigned',
    acknowledgement_key TEXT,
    score INTEGER CHECK (score BETWEEN 0 AND 100),
    audit_feedback TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
-- status: 'assigned' (fresh/reopened, awaiting human action) | 'completed' (checked off,
-- had no ingredients_used to deduct) | 'acknowledged' (checked off, ingredients deducted -
-- locked) | 'cancelled' (soft-cancelled, no deduction) | 'expired' (still 'assigned' 2+
-- hours after created_at - see expire_stale_prep_tasks and the expire_prep_tasks job).

CREATE TABLE IF NOT EXISTS inventory_transactions (
    id INTEGER PRIMARY KEY,
    inventory_id INTEGER NOT NULL REFERENCES inventory(id),
    quantity_change REAL NOT NULL CHECK (quantity_change <> 0),
    quantity_before REAL NOT NULL,
    quantity_after REAL NOT NULL,
    reason TEXT NOT NULL,
    source_type TEXT,
    source_id INTEGER,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS shopping_items (
    id INTEGER PRIMARY KEY,
    item_name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    proposed_quantity REAL NOT NULL CHECK (proposed_quantity > 0),
    unit TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id INTEGER PRIMARY KEY,
    agent_role TEXT NOT NULL,
    job_name TEXT NOT NULL,
    status TEXT NOT NULL,
    result TEXT,
    error TEXT,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    finished_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id TEXT PRIMARY KEY,
    messages_json TEXT NOT NULL DEFAULT '[]',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    cc_emails TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    favorite_recipes TEXT NOT NULL DEFAULT '[]',
    notify_on_task_creation INTEGER NOT NULL DEFAULT 1,
    restrictions TEXT NOT NULL DEFAULT '[
        {"id":"no_nonveg_lunch","label":"No egg/meat/fish in lunches","category":"dietary","enabled":true,"scope":"per_meal"},
        {"id":"lunch_variety","label":"Weekday lunches must be distinct","category":"variety","enabled":true,"value":5,"scope":"week"}
    ]',
    allow_recipe_invention INTEGER NOT NULL DEFAULT 1,
    allow_unapproved_recipes INTEGER NOT NULL DEFAULT 1,
    skip_meals TEXT NOT NULL DEFAULT '{}',
    preferred_tags TEXT NOT NULL DEFAULT '[]',
    excluded_tags TEXT NOT NULL DEFAULT '[]',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
-- restrictions: JSON list of {id, label, category, enabled, scope, value?} - household-
-- configurable planning/judging rules. scope is "per_meal" (judged per weekly_menu row by
-- menu_audit) or "week" (judged once per week, across the whole saved menu, by
-- weekly_plan_audit - see the weekly_plans table below). value is an optional rule-
-- specific parameter (e.g. lunch_variety's minimum distinct-preparations count). This
-- list is read live by get_household_preferences - restrictions are never hardcoded in
-- agent prompts or in a deterministic validator (see weekly_plans below for why).
-- skip_meals: JSON object of {day_of_week: [meal_type, ...]} - slots the household wants
-- left unplanned for that week (e.g. away from home), consulted by the weekly_menu job.

CREATE TABLE IF NOT EXISTS household_members (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    dietary_preferences TEXT NOT NULL DEFAULT '[]',
    health_conditions TEXT NOT NULL DEFAULT '[]',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recipes (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    recipe TEXT NOT NULL,
    embedding TEXT NOT NULL,
    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
    score INTEGER CHECK (score BETWEEN 0 AND 100),
    audit_feedback TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
-- recipe: the full structured recipe (name, description, origin, serves, ingredients,
-- instructions, macros_per_serving, meal_types, tags, source) as JSON - the single
-- source of truth for that recipe's content. description is a short (a sentence or two)
-- household-facing summary of the dish, required like name. tags carries every
-- descriptive label (diet category, allergen/
-- restriction, nutrition character, etc) per the household's recipe catalog standards -
-- there is no separate dietary_flags field. embedding: a JSON array of floats (one
-- vector per recipe, built from the whole recipe text - see kitchendb/embeddings.py),
-- always kept in sync with recipe by add_recipe/update_recipe/reindex_recipes so the
-- two never drift apart. rating is a separate household preference signal (1-5, human-
-- or chat-set) that never touches embedding. score/audit_feedback are the Food
-- Inspector's judgement (NULL = not yet audited) - reset to NULL by update_recipe on
-- every edit, same convention as weekly_menu. No uniqueness constraint on name - a
-- household may keep more than one version of the same dish.

-- Keyword half of search_recipes' hybrid search (see kitchendb/keyword_search.py). A
-- standalone (not content=-linked) FTS5 table whose rowid is always the matching
-- recipes.id - kept in sync explicitly by add_recipe/update_recipe/delete_recipe/
-- reindex_recipes (no SQL triggers; every other write path in this schema is synced
-- the same explicit way from Python, e.g. the embedding column above).
CREATE VIRTUAL TABLE IF NOT EXISTS recipes_fts USING fts5(
    name, ingredients, tags, instructions,
    tokenize = 'porter unicode61'
);
