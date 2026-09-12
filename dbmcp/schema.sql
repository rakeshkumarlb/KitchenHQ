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

CREATE TABLE IF NOT EXISTS wastage_log (
    id INTEGER PRIMARY KEY,
    item_name TEXT NOT NULL,
    quantity_wasted REAL NOT NULL CHECK (quantity_wasted > 0),
    date_logged DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS weekly_menu (
    id INTEGER PRIMARY KEY,
    day_of_week TEXT NOT NULL,
    meal_type TEXT NOT NULL,
    dish_name TEXT NOT NULL,
    is_kid_friendly BOOLEAN NOT NULL,
    macros TEXT NOT NULL,
    ingredients TEXT NOT NULL,
    full_recipe TEXT NOT NULL DEFAULT '',
    score INTEGER CHECK (score BETWEEN 0 AND 100),
    audit_feedback TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
-- Exactly one row per (day_of_week, meal_type); the unique index makes
-- add_weekly_menu_item a true atomic upsert.
CREATE UNIQUE INDEX IF NOT EXISTS idx_weekly_menu_day_meal
    ON weekly_menu (day_of_week, meal_type);

CREATE TABLE IF NOT EXISTS detailed_prep_schedule (
    id INTEGER PRIMARY KEY,
    trigger_day TEXT NOT NULL,
    trigger_time TEXT NOT NULL,
    task_type TEXT NOT NULL,
    detailed_instructions TEXT NOT NULL,
    ingredients_used TEXT NOT NULL DEFAULT '[]',
    is_completed BOOLEAN NOT NULL DEFAULT 0,
    human_notes TEXT,
    status TEXT NOT NULL DEFAULT 'proposed',
    acknowledgement_key TEXT,
    score INTEGER CHECK (score BETWEEN 0 AND 100),
    audit_feedback TEXT
);

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
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS household_members (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    dietary_preferences TEXT NOT NULL DEFAULT '[]',
    health_conditions TEXT NOT NULL DEFAULT '[]',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
