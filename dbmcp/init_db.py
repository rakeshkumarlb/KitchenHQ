"""KitchenHQ database tools exposed through FastAPI and FastMCP."""

from __future__ import annotations

import os
import json
import re
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, Field, field_validator

from units import CANONICAL_UNITS, canonicalize_inventory_unit, convert

# Email notifications now live in agents/app/email/ (the agent is the only
# process that sends mail). dbmcp owns data only - it has no SMTP config and no
# send_*_email tools/routes any more.

DATABASE_PATH = Path(os.environ.get("KITCHEN_DB_PATH", Path(__file__).with_name("kitchen.db")))
VALID_DAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
VALID_MEAL_TYPES = {"breakfast", "lunch", "snack", "dinner"}
# weekly_menu.ingredients / .full_recipe are JSON string arrays (a list of short
# plain-text lines). This is the generic method used for every seeded dish.
_SEED_RECIPE_STEPS = [
    "Wash and prepare every ingredient, then measure the spices and liquids into separate bowls.",
    "Heat a wide pan over medium heat and add the oil. Add the aromatics and cook for 2 minutes until fragrant.",
    "Add the main ingredients and cook for 5 minutes, stirring often so the edges colour evenly.",
    "Add the grains, sauce, or liquid, reduce the heat, cover, and cook for 10 minutes until tender.",
    "Remove the lid, taste, and adjust salt, acidity, and seasoning. Rest for 2 minutes.",
    "Plate while warm, finish with the fresh garnish, and serve immediately.",
]
_MENU_LINES_LIMIT = 40
allowed_hosts = [host.strip() for host in os.environ.get("MCP_ALLOWED_HOSTS", "localhost:18000,127.0.0.1:18000,dbmcp:18000,kitchenhq-db-mcp:18000").split(",") if host.strip()]
mcp = FastMCP("KitchenHQ Database", transport_security=TransportSecuritySettings(allowed_hosts=allowed_hosts))

API_KEY_HEADER = "X-API-Key"
PUBLIC_PATHS = {"/api/health"}


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY, item_name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                category TEXT NOT NULL, quantity REAL NOT NULL,
                unit TEXT NOT NULL, minimum_threshold REAL NOT NULL DEFAULT 0 CHECK (minimum_threshold >= 0),
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS wastage_log (
                id INTEGER PRIMARY KEY, item_name TEXT NOT NULL,
                quantity_wasted REAL NOT NULL CHECK (quantity_wasted > 0),
                date_logged DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS weekly_menu (
                id INTEGER PRIMARY KEY, day_of_week TEXT NOT NULL, meal_type TEXT NOT NULL,
                dish_name TEXT NOT NULL, is_kid_friendly BOOLEAN NOT NULL, macros TEXT NOT NULL,
                ingredients TEXT NOT NULL, full_recipe TEXT NOT NULL DEFAULT '',
                kid_rating INTEGER CHECK (kid_rating BETWEEN 1 AND 5),
                human_feedback TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS detailed_prep_schedule (
                id INTEGER PRIMARY KEY, trigger_day TEXT NOT NULL, trigger_time TEXT NOT NULL,
                task_type TEXT NOT NULL,
                detailed_instructions TEXT NOT NULL,
                ingredients_used TEXT NOT NULL DEFAULT '[]',
                is_completed BOOLEAN NOT NULL DEFAULT 0, human_notes TEXT,
                status TEXT NOT NULL DEFAULT 'proposed',
                acknowledgement_key TEXT
            );
        """)
        menu_columns = {row[1] for row in connection.execute("PRAGMA table_info(weekly_menu)")}
        if "full_recipe" not in menu_columns:
            connection.execute("ALTER TABLE weekly_menu ADD COLUMN full_recipe TEXT NOT NULL DEFAULT ''")
        # `updated_at` records when a slot was last (re)planned - refreshed on every
        # add_weekly_menu_item upsert. SQLite rejects `ADD COLUMN ... DEFAULT
        # CURRENT_TIMESTAMP`, so add it nullable and backfill once.
        if "updated_at" not in menu_columns:
            connection.execute("ALTER TABLE weekly_menu ADD COLUMN updated_at DATETIME")
            connection.execute("UPDATE weekly_menu SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL")
        # weekly_menu holds exactly one row per (day_of_week, meal_type). Normalize
        # casing, drop any duplicate rows left by older code paths or by two
        # weekly_menu runs racing on the old check-then-insert, then enforce it with a
        # unique index so add_weekly_menu_item is a true atomic upsert from here on.
        connection.execute("UPDATE weekly_menu SET meal_type = LOWER(TRIM(meal_type)) WHERE meal_type <> LOWER(TRIM(meal_type))")
        connection.execute("UPDATE weekly_menu SET day_of_week = LOWER(TRIM(day_of_week)) WHERE day_of_week <> LOWER(TRIM(day_of_week))")
        connection.execute("DELETE FROM weekly_menu WHERE id NOT IN (SELECT MAX(id) FROM weekly_menu GROUP BY day_of_week, meal_type)")
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_weekly_menu_day_meal ON weekly_menu (day_of_week, meal_type)")
        if connection.execute("SELECT 1 FROM inventory WHERE item_name = 'Baby spinach'").fetchone() is None:
            connection.executemany(
                "INSERT INTO inventory (item_name, category, quantity, unit, minimum_threshold) VALUES (?, ?, ?, ?, ?)",
                [
                    ("Baby spinach", "Fresh", 2, "pcs", 1),
                    ("Paneer", "Dairy", 450, "g", 250),
                    ("Brown rice", "Pantry", 1.8, "kg", 1),
                    ("Cherry tomatoes", "Fresh", 350, "g", 200),
                    ("Eggs", "Proteins", 10, "pcs", 6),
                    ("Greek yogurt", "Dairy", 700, "g", 300),
                ],
            )
        if connection.execute("SELECT COUNT(*) FROM weekly_menu").fetchone()[0] < 28:
            # INSERT OR IGNORE against the unique (day_of_week, meal_type) index: a
            # re-seed after the agent overwrote rows leaves existing slots untouched
            # instead of duplicating them.
            connection.executemany(
                "INSERT OR IGNORE INTO weekly_menu (day_of_week, meal_type, dish_name, is_kid_friendly, macros, ingredients, full_recipe) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (day, meal_type.lower(), dish, 1, macros,
                     json.dumps([part.strip() for part in ingredients.split(",") if part.strip()]),
                     json.dumps(_SEED_RECIPE_STEPS))
                    for day, meals in {
                        "monday": [("Breakfast", "Spinach masala eggs", "26g protein  /  18g carbs  /  20g fat", "Eggs, baby spinach, tomatoes"), ("Lunch", "Paneer tikka bowls", "32g protein  /  48g carbs  /  18g fat", "Paneer, brown rice, spinach, yogurt"), ("Snack", "Yogurt fruit crunch", "18g protein  /  26g carbs  /  8g fat", "Greek yogurt, banana, seeds"), ("Dinner", "Lemon herb rice skillet", "24g protein  /  52g carbs  /  14g fat", "Brown rice, spinach, yogurt")],
                        "tuesday": [("Breakfast", "Savory paneer toast", "29g protein  /  31g carbs  /  16g fat", "Paneer, wholegrain bread, tomatoes"), ("Lunch", "Paneer tomato rice bowl", "28g protein  /  46g carbs  /  16g fat", "Paneer, brown rice, cherry tomatoes, spinach"), ("Snack", "Spiced yogurt dip", "14g protein  /  12g carbs  /  7g fat", "Greek yogurt, cucumber, herbs"), ("Dinner", "Tikka rice lettuce cups", "30g protein  /  39g carbs  /  15g fat", "Paneer, brown rice, lettuce")],
                        "wednesday": [("Breakfast", "Green breakfast bowl", "22g protein  /  35g carbs  /  12g fat", "Eggs, spinach, brown rice"), ("Lunch", "Green goddess rice", "24g protein  /  54g carbs  /  14g fat", "Brown rice, spinach, yogurt"), ("Snack", "Tomato paneer skewers", "19g protein  /  14g carbs  /  9g fat", "Paneer, cherry tomatoes, herbs"), ("Dinner", "Creamy spinach eggs", "27g protein  /  20g carbs  /  19g fat", "Eggs, spinach, Greek yogurt")],
                        "thursday": [("Breakfast", "Yogurt oat parfait", "20g protein  /  42g carbs  /  10g fat", "Greek yogurt, oats, banana"), ("Lunch", "Roasted paneer salad", "35g protein  /  20g carbs  /  21g fat", "Paneer, cherry tomatoes, spinach"), ("Snack", "Cucumber raita cup", "12g protein  /  10g carbs  /  5g fat", "Greek yogurt, cucumber, herbs"), ("Dinner", "Golden egg rice", "25g protein  /  46g carbs  /  15g fat", "Eggs, brown rice, spinach")],
                        "friday": [("Breakfast", "Paneer breakfast hash", "31g protein  /  34g carbs  /  17g fat", "Paneer, brown rice, tomatoes"), ("Lunch", "Paneer spinach wraps", "30g protein  /  36g carbs  /  17g fat", "Paneer, spinach, yogurt, wholegrain wraps"), ("Snack", "Cinnamon yogurt bowl", "17g protein  /  24g carbs  /  6g fat", "Greek yogurt, banana, seeds"), ("Dinner", "Friday tomato rice", "23g protein  /  55g carbs  /  12g fat", "Brown rice, tomatoes, eggs")],
                        "saturday": [("Breakfast", "Herbed egg scramble", "25g protein  /  16g carbs  /  18g fat", "Eggs, spinach, herbs"), ("Lunch", "Paneer rainbow plate", "34g protein  /  32g carbs  /  19g fat", "Paneer, brown rice, tomatoes"), ("Snack", "Yogurt cucumber cups", "13g protein  /  11g carbs  /  5g fat", "Greek yogurt, cucumber"), ("Dinner", "One-pan spinach pilaf", "21g protein  /  51g carbs  /  13g fat", "Brown rice, spinach, yogurt")],
                        "sunday": [("Breakfast", "Weekend masala omelet", "27g protein  /  14g carbs  /  20g fat", "Eggs, tomatoes, spinach"), ("Lunch", "Sunday paneer bowls", "33g protein  /  49g carbs  /  18g fat", "Paneer, brown rice, yogurt"), ("Snack", "Fruit and yogurt lassi", "15g protein  /  30g carbs  /  5g fat", "Greek yogurt, banana, herbs"), ("Dinner", "Comfort tomato shakshuka", "28g protein  /  24g carbs  /  16g fat", "Eggs, tomatoes, spinach")],
                    }.items() for meal_type, dish, macros, ingredients in meals
                ],
            )
        # Migration: `ingredients_created` and `consumption_json` were dropped, and
        # `ingredients_used`/`detailed_instructions` changed from free text to validated
        # JSON (see add_detailed_prep_schedule's docstring for the shape). SQLite can't
        # ALTER away a column, so an old row is rebuilt once (guarded on
        # `ingredients_created` still being present); best-effort carries old
        # consumption_json (inventory_id-keyed) over to the new item_name-keyed
        # ingredients_used by resolving each id, and wraps a legacy free-text
        # detailed_instructions/ingredients_used string as a single-line JSON array.
        prep_columns = {row[1] for row in connection.execute("PRAGMA table_info(detailed_prep_schedule)")}
        if "ingredients_created" in prep_columns:
            old_rows = [dict(row) for row in connection.execute("SELECT * FROM detailed_prep_schedule")]
            connection.executescript("""
                ALTER TABLE detailed_prep_schedule RENAME TO _prep_schedule_migrate;
                CREATE TABLE detailed_prep_schedule (
                    id INTEGER PRIMARY KEY, trigger_day TEXT NOT NULL, trigger_time TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    detailed_instructions TEXT NOT NULL,
                    ingredients_used TEXT NOT NULL DEFAULT '[]',
                    is_completed BOOLEAN NOT NULL DEFAULT 0, human_notes TEXT,
                    status TEXT NOT NULL DEFAULT 'proposed',
                    acknowledgement_key TEXT
                );
            """)

            def _as_line_list(value: Any) -> list[str]:
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        return [str(line) for line in parsed]
                except (TypeError, ValueError):
                    pass
                return [str(value)] if value else []

            for row in old_rows:
                try:
                    old_consumption = json.loads(row.get("consumption_json") or "[]")
                except (TypeError, ValueError):
                    old_consumption = []
                new_ingredients = []
                for entry in old_consumption if isinstance(old_consumption, list) else []:
                    inventory_row = connection.execute(
                        "SELECT item_name FROM inventory WHERE id = ?", (entry.get("inventory_id"),)
                    ).fetchone()
                    if inventory_row is not None:
                        new_ingredients.append({
                            "item_name": inventory_row["item_name"],
                            "quantity": entry.get("quantity"),
                            "unit": entry.get("unit", ""),
                        })
                connection.execute(
                    "INSERT INTO detailed_prep_schedule (id, trigger_day, trigger_time, task_type, detailed_instructions, ingredients_used, is_completed, human_notes, status, acknowledgement_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        row["id"], row["trigger_day"], row["trigger_time"], row["task_type"],
                        json.dumps(_as_line_list(row["detailed_instructions"])),
                        json.dumps(new_ingredients),
                        row["is_completed"], row["human_notes"],
                        row.get("status", "proposed") or "proposed",
                        row.get("acknowledgement_key"),
                    ),
                )
            connection.execute("DROP TABLE _prep_schedule_migrate")

        if connection.execute("SELECT 1 FROM detailed_prep_schedule WHERE task_type = 'Morning prep'").fetchone() is None:
            def _ingredients_used(*wants: tuple[str, float, str]) -> str:
                return json.dumps([{"item_name": name, "quantity": quantity, "unit": unit} for name, quantity, unit in wants])

            connection.executemany(
                "INSERT INTO detailed_prep_schedule (trigger_day, trigger_time, task_type, detailed_instructions, ingredients_used) VALUES (?, ?, ?, ?, ?)",
                [
                    ("monday", "07:30", "Morning prep",
                     json.dumps(["Wash the spinach and pat it dry.", "Portion the Greek yogurt into the day's serving bowls."]),
                     _ingredients_used(("Baby spinach", 1, "pcs"), ("Greek yogurt", 200, "g"))),
                    ("tuesday", "17:00", "Dinner prep",
                     json.dumps(["Dice the cherry tomatoes.", "Press the paneer to remove excess water, then cube it."]),
                     _ingredients_used(("Cherry tomatoes", 150, "g"), ("Paneer", 200, "g"))),
                    ("wednesday", "08:00", "Batch prep",
                     json.dumps(["Rinse the brown rice.", "Cook until tender, then spread it in shallow containers to cool quickly."]),
                     _ingredients_used(("Brown rice", 0.5, "kg"))),
                ],
            )
        columns = {row[1] for row in connection.execute("PRAGMA table_info(detailed_prep_schedule)")}
        if "status" not in columns:
            connection.execute("ALTER TABLE detailed_prep_schedule ADD COLUMN status TEXT NOT NULL DEFAULT 'proposed'")
        if "acknowledgement_key" not in columns:
            connection.execute("ALTER TABLE detailed_prep_schedule ADD COLUMN acknowledgement_key TEXT")
        connection.execute("UPDATE detailed_prep_schedule SET status = 'completed' WHERE is_completed = 1 AND status = 'proposed'")
        connection.executescript("""
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
        """)
        connection.execute("INSERT OR IGNORE INTO user_profile (id, name) VALUES (1, 'Alex Kim')")
        # Migration: `phone` was dropped and `cc_emails` / `favorite_recipes` added.
        # SQLite can't ALTER away a column, so an old row is rebuilt once (guarded on
        # `phone` still being present); newer DBs just take the ADD COLUMN backfills.
        profile_columns = {row[1] for row in connection.execute("PRAGMA table_info(user_profile)")}
        if "phone" in profile_columns:
            connection.executescript("""
                ALTER TABLE user_profile RENAME TO _user_profile_migrate;
                CREATE TABLE user_profile (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    name TEXT NOT NULL DEFAULT '',
                    email TEXT NOT NULL DEFAULT '',
                    cc_emails TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    favorite_recipes TEXT NOT NULL DEFAULT '[]',
                    notify_on_task_creation INTEGER NOT NULL DEFAULT 1,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO user_profile (id, name, email, notes, notify_on_task_creation, updated_at)
                    SELECT id, name, email, notes, notify_on_task_creation, updated_at FROM _user_profile_migrate;
                DROP TABLE _user_profile_migrate;
            """)
        else:
            if "cc_emails" not in profile_columns:
                connection.execute("ALTER TABLE user_profile ADD COLUMN cc_emails TEXT NOT NULL DEFAULT ''")
            if "favorite_recipes" not in profile_columns:
                connection.execute("ALTER TABLE user_profile ADD COLUMN favorite_recipes TEXT NOT NULL DEFAULT '[]'")
        # Migration: shopping_lists is gone - shopping_items is now a single flat,
        # unique-by-item_name pending pool (no more per-run "list" grouping; a purchase
        # deletes its row instead of flipping a list's status). Roll forward whatever was
        # still pending (parent list not yet purchased) under the new unique-name upsert
        # rule, merging any name collisions by summing quantity; anything already
        # purchased is history that lived only for the old idempotent-replay check and
        # isn't needed once shopping_items itself is deleted-on-purchase.
        shopping_items_columns = {row[1] for row in connection.execute("PRAGMA table_info(shopping_items)")}
        if "shopping_list_id" in shopping_items_columns:
            has_shopping_lists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'shopping_lists'"
            ).fetchone() is not None
            if has_shopping_lists:
                pending = connection.execute("""
                    SELECT si.item_name, si.proposed_quantity, si.unit
                    FROM shopping_items si
                    JOIN shopping_lists sl ON sl.id = si.shopping_list_id
                    WHERE sl.status <> 'purchased' AND si.status <> 'purchased'
                    ORDER BY si.id
                """).fetchall()
            else:
                pending = []
            connection.execute("DROP TABLE shopping_items")
            connection.execute("""
                CREATE TABLE shopping_items (
                    id INTEGER PRIMARY KEY,
                    item_name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    proposed_quantity REAL NOT NULL CHECK (proposed_quantity > 0),
                    unit TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            for row in pending:
                connection.execute(
                    """
                    INSERT INTO shopping_items (item_name, proposed_quantity, unit) VALUES (?, ?, ?)
                    ON CONFLICT(item_name) DO UPDATE SET
                        proposed_quantity = proposed_quantity + excluded.proposed_quantity,
                        unit = excluded.unit,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (row["item_name"], row["proposed_quantity"], row["unit"]),
                )
        connection.execute("DROP TABLE IF EXISTS shopping_lists")
        # Migration: drop the historical `quantity >= 0` / `quantity_after >= 0` CHECK
        # constraints so prep acknowledgements can push a tracked balance negative
        # (SQLite can't ALTER away a CHECK - the table has to be rebuilt). Guarded on
        # the constraint text still being present, so it runs once per old database.
        inventory_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'inventory'"
        ).fetchone()
        if inventory_sql and "quantity >= 0" in inventory_sql[0]:
            connection.executescript("""
                ALTER TABLE inventory RENAME TO _inventory_migrate;
                CREATE TABLE inventory (
                    id INTEGER PRIMARY KEY, item_name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    category TEXT NOT NULL, quantity REAL NOT NULL,
                    unit TEXT NOT NULL, minimum_threshold REAL NOT NULL DEFAULT 0 CHECK (minimum_threshold >= 0),
                    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO inventory (id, item_name, category, quantity, unit, minimum_threshold, last_updated)
                    SELECT id, item_name, category, quantity, unit, minimum_threshold, last_updated FROM _inventory_migrate;
                DROP TABLE _inventory_migrate;
            """)
        transactions_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'inventory_transactions'"
        ).fetchone()
        if transactions_sql and "quantity_after >= 0" in transactions_sql[0]:
            connection.executescript("""
                ALTER TABLE inventory_transactions RENAME TO _transactions_migrate;
                CREATE TABLE inventory_transactions (
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
                INSERT INTO inventory_transactions (id, inventory_id, quantity_change, quantity_before, quantity_after, reason, source_type, source_id, idempotency_key, created_at)
                    SELECT id, inventory_id, quantity_change, quantity_before, quantity_after, reason, source_type, source_id, idempotency_key, created_at FROM _transactions_migrate;
                DROP TABLE _transactions_migrate;
            """)

        # Unit-of-measure normalization: every inventory deduction/intake now
        # converts the incoming quantity into the row's *stored* unit before
        # touching the balance (see units.py). Canonicalize legacy alias
        # spellings in the two tables that feed that math so a row saved as
        # "kilograms"/"litre"/"pieces" lines up with the "kg"/"l"/"pcs" the
        # converter expects, and fold the old "bags" pack-unit onto "pcs".
        # Balances themselves are left untouched (fix-forward only).
        for _unit_table in ("inventory", "shopping_items"):
            for _row in connection.execute(f"SELECT id, unit FROM {_unit_table}").fetchall():
                _canon = canonicalize_inventory_unit(_row["unit"])
                if _canon is None and str(_row["unit"]).strip().lower().rstrip("s") == "bag":
                    _canon = "pcs"
                if _canon and _canon != _row["unit"]:
                    connection.execute(
                        f"UPDATE {_unit_table} SET unit = ? WHERE id = ?", (_canon, _row["id"])
                    )


def _record(table: str, record_id: int) -> dict[str, Any]:
    with _connect() as connection:
        row = connection.execute(f"SELECT * FROM {table} WHERE id = ?", (record_id,)).fetchone()
    if row is None:
        raise ValueError(f"No {table} record found for id {record_id}")
    return dict(row)


def _validate_day(day_of_week: str) -> str:
    normalized = day_of_week.strip().lower()
    if normalized not in VALID_DAYS:
        raise ValueError("day_of_week must be a full weekday name")
    return normalized


def _validate_meal_type(meal_type: str) -> str:
    normalized = meal_type.strip().lower()
    if normalized not in VALID_MEAL_TYPES:
        raise ValueError(f"meal_type must be one of {sorted(VALID_MEAL_TYPES)}")
    return normalized


def _clean_menu_lines(value: Any, *, field: str, required: bool) -> list[str]:
    """Normalize a weekly_menu ingredients/full_recipe value into a clean string list.

    The columns store a JSON string array (a list of short plain-text lines). Accepts a
    list; trims blanks; caps the count so a runaway model can't bloat a row.
    """
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list of strings")
    lines = [str(item).strip() for item in value if str(item).strip()]
    if required and not lines:
        raise ValueError(f"{field} must contain at least one non-empty string")
    if len(lines) > _MENU_LINES_LIMIT:
        raise ValueError(f"{field} cannot have more than {_MENU_LINES_LIMIT} items")
    return lines


@mcp.tool()
def get_inventory() -> list[dict[str, Any]]:
    """Read the current pantry inventory."""
    with _connect() as connection:
        return [dict(row) for row in connection.execute("SELECT * FROM inventory ORDER BY category, item_name")]


@mcp.tool()
def get_weekly_menu() -> list[dict[str, Any]]:
    """Read the saved weekly menu."""
    with _connect() as connection:
        return [dict(row) for row in connection.execute("SELECT * FROM weekly_menu ORDER BY id")]


@mcp.tool()
def get_prep_schedules() -> list[dict[str, Any]]:
    """Read preparation schedules (cancelled tasks are excluded)."""
    with _connect() as connection:
        return [dict(row) for row in connection.execute("SELECT * FROM detailed_prep_schedule WHERE status <> 'cancelled' ORDER BY is_completed, id")]


@mcp.tool()
def get_shopping_items() -> list[dict[str, Any]]:
    """Read the pending shopping list - one row per item still needing to be bought.

    There is only ever one shopping list: every row here is currently pending. An item
    disappears from this list the moment it's acknowledged as purchased (see
    acknowledge_shopping_items) - nothing here ever carries a "purchased" status."""
    with _connect() as connection:
        return [dict(row) for row in connection.execute("SELECT * FROM shopping_items ORDER BY item_name")]


def _menu_policy_violations(menu_items: list[dict[str, Any]]) -> list[str]:
    violations = []
    restricted_lunch_terms = ("egg", "chicken", "beef", "pork", "fish", "meat", "turkey", "seafood")
    lunch_dishes = []
    for item in menu_items:
        meal_type = str(item.get("meal_type", "")).strip().lower()
        dish_name = str(item.get("dish_name", "")).strip()
        ingredients = str(item.get("ingredients", "")).lower()
        #macros = str(item.get("macros", "")).lower()
        #if not re.search(r"\d+(?:\.\d+)?\s*g\s*protein", macros) or not re.search(r"\d+(?:\.\d+)?\s*g\s*carbs?", macros) or not re.search(r"\d+(?:\.\d+)?\s*g\s*fat", macros):
            #violations.append(f"{dish_name or 'Unnamed meal'} must include protein, carbs, and fat macros")
        if meal_type == "lunch":
            lunch_dishes.append(dish_name.lower())
            restricted = [term for term in restricted_lunch_terms if re.search(rf"\b{re.escape(term)}\b", f"{dish_name.lower()} {ingredients}")]
            if restricted:
                violations.append(f"{dish_name} contains restricted lunch ingredient: {restricted[0]}")
    if len(lunch_dishes) >= 5 and len(set(lunch_dishes)) < 5:
        violations.append("Weekday lunches must contain five distinct preparations")
    return violations


@mcp.tool()
def validate_weekly_menu_policy(menu_items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Validate macros, school lunch restrictions, and weekday lunch variety."""
    if menu_items is None:
        with _connect() as connection:
            menu_items = [dict(row) for row in connection.execute("SELECT * FROM weekly_menu ORDER BY id")]
    violations = _menu_policy_violations(menu_items)
    return {"valid": not violations, "violations": violations}


@mcp.tool()
def add_inventory(item_name: str, quantity: float, unit: str, category: str = "Pantry", minimum_threshold: float = 0) -> dict[str, Any]:
    """Add a new ingredient to inventory.

    `unit` is the row's canonical stock unit and must be one of g, kg, ml, l, pcs
    (common aliases like "grams"/"litre"/"pieces" are accepted and stored in the
    canonical short form). Every later deduction/intake converts its own quantity
    into this unit, so pick the one you want the running balance reported in.
    """
    if not item_name.strip() or not unit.strip():
        raise ValueError("item_name and unit are required")
    if quantity < 0 or minimum_threshold < 0:
        raise ValueError("quantity and minimum_threshold cannot be negative")
    canonical_unit = canonicalize_inventory_unit(unit)
    if canonical_unit is None:
        raise ValueError(f"unit must be one of {', '.join(CANONICAL_UNITS)} (or a recognized alias); got '{unit.strip()}'")
    with _connect() as connection:
        try:
            cursor = connection.execute("INSERT INTO inventory (item_name, category, quantity, unit, minimum_threshold) VALUES (?, ?, ?, ?, ?)", (item_name.strip(), category.strip(), quantity, canonical_unit, minimum_threshold))
        except sqlite3.IntegrityError as error:
            raise ValueError(f"Inventory item already exists: {item_name}") from error
    return _record("inventory", cursor.lastrowid)


@mcp.tool()
def adjust_inventory_quantity(item_id: int, quantity_change: float) -> dict[str, Any]:
    """Increase or decrease an existing ingredient's quantity."""
    if quantity_change == 0:
        raise ValueError("quantity_change cannot be zero")
    with _connect() as connection:
        item = connection.execute("SELECT quantity FROM inventory WHERE id = ?", (item_id,)).fetchone()
        if item is None:
            raise ValueError(f"No inventory record found for id {item_id}")
        new_quantity = item["quantity"] + quantity_change
        if new_quantity < 0:
            raise ValueError("quantity cannot become negative")
        connection.execute("UPDATE inventory SET quantity = ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?", (new_quantity, item_id))
    return _record("inventory", item_id)


@mcp.tool()
def remove_or_discard_inventory(item_id: int, quantity: float, reason: str = "Discarded") -> dict[str, Any]:
    """Remove quantity from inventory and record it as discarded."""
    if quantity <= 0:
        raise ValueError("quantity must be greater than zero")
    with _connect() as connection:
        item = connection.execute("SELECT item_name, quantity FROM inventory WHERE id = ?", (item_id,)).fetchone()
        if item is None:
            raise ValueError(f"No inventory record found for id {item_id}")
        if quantity > item["quantity"]:
            raise ValueError("discarded quantity cannot exceed available quantity")
        connection.execute("UPDATE inventory SET quantity = quantity - ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?", (quantity, item_id))
        connection.execute("INSERT INTO wastage_log (item_name, quantity_wasted) VALUES (?, ?)", (f"{item['item_name']} ({reason.strip() or 'Discarded'})", quantity))
    return _record("inventory", item_id)


@mcp.tool()
def add_weekly_menu_item(day_of_week: str, meal_type: str, dish_name: str, is_kid_friendly: bool, macros: str, ingredients: list[str], full_recipe: list[str] | None = None) -> dict[str, Any]:
    """Add or replace one meal in the weekly menu.

    This is a true upsert on (day_of_week, meal_type): a plan is built by calling this
    once per slot (all seven days monday..sunday x breakfast/lunch/snack/dinner).
    Re-saving a slot overwrites it (and refreshes its updated_at); a unique index
    guarantees exactly one row per slot even under concurrent runs.

    Parameters:
      day_of_week: Day name for the meal slot (for example: "Monday", "Tuesday", etc.).
      meal_type: Meal slot type (for example: "breakfast", "lunch", "snack", or "dinner").
      dish_name: Human-readable name of the dish being planned for that meal slot.
      is_kid_friendly: Whether the dish is appropriate for children. Defaults to True.
      macros: Optional nutrition summary string for the dish, such as a textual macro breakdown.
      ingredients: ordered list of ingredient strings with quantities, plain text (no
        HTML / markdown). Stored as a JSON array; the UI and emails render it as a list.
      full_recipe: ordered list of method-step strings, plain text (no HTML / markdown).
        Stored as a JSON array; rendered as a numbered list.
    """
    day = _validate_day(day_of_week)
    meal = _validate_meal_type(meal_type)
    ingredient_lines = _clean_menu_lines(ingredients, field="ingredients", required=True)
    recipe_lines = _clean_menu_lines(full_recipe or [], field="full_recipe", required=False)
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO weekly_menu (day_of_week, meal_type, dish_name, is_kid_friendly, macros, ingredients, full_recipe, kid_rating, human_feedback, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(day_of_week, meal_type) DO UPDATE SET
                dish_name = excluded.dish_name,
                is_kid_friendly = excluded.is_kid_friendly,
                macros = excluded.macros,
                ingredients = excluded.ingredients,
                full_recipe = excluded.full_recipe,
                kid_rating = NULL,
                human_feedback = NULL,
                updated_at = CURRENT_TIMESTAMP
            """,
            (day, meal, dish_name.strip(), int(is_kid_friendly), macros, json.dumps(ingredient_lines), json.dumps(recipe_lines), None, None),
        )
        row = connection.execute("SELECT * FROM weekly_menu WHERE day_of_week = ? AND meal_type = ?", (day, meal)).fetchone()
    return dict(row)


# --- soft-deleted: no caller ----------------------------------------------------
# `add_weekly_menu_plan` (whole-week validate-then-write) had exactly one entry point,
# `POST /api/weekly-menu/plan`, which nothing calls (chatui builds the week slot by
# slot; the agent uses add_weekly_menu_item + validate_weekly_menu_policy). Kept
# commented for reference; delete once confirmed unneeded.
#
# def add_weekly_menu_plan(menu_items: list[dict[str, Any]]) -> dict[str, Any]:
#     """Validate and save a complete meal plan atomically."""
#     if len(menu_items) < 5:
#         raise ValueError("a weekly plan requires at least five menu items")
#     for item in menu_items:
#         _validate_day(str(item.get("day_of_week", "")))
#         _validate_meal_type(str(item.get("meal_type", "")))
#     policy = validate_weekly_menu_policy(menu_items)
#     if not policy["valid"]:
#         raise ValueError("Meal plan policy violations: " + "; ".join(policy["violations"]))
#     saved = []
#     for item in menu_items:
#         saved.append(
#             add_weekly_menu_item(
#                 day_of_week=str(item["day_of_week"]),
#                 meal_type=str(item["meal_type"]),
#                 dish_name=str(item["dish_name"]),
#                 is_kid_friendly=bool(item.get("is_kid_friendly", False)),
#                 macros=str(item["macros"]),
#                 ingredients=list(item.get("ingredients") or []),
#                 full_recipe=list(item.get("full_recipe") or []),
#             )
#         )
#     return {"items": saved}


FAVORITE_RECIPES_LIMIT = 10


def _sync_favorite_recipes(connection: sqlite3.Connection, dish_name: str, rating: int) -> None:
    """Keep user_profile.favorite_recipes as the <=10 most recently top-rated dishes.

    A 4- or 5-star rating moves the dish to the front (newest first); any lower rating
    demotes it out. The list is trimmed to FAVORITE_RECIPES_LIMIT, so an older
    favourite falls off once ten fresher dishes have been top-rated.
    """
    dish = (dish_name or "").strip()
    if not dish:
        return
    row = connection.execute("SELECT favorite_recipes FROM user_profile WHERE id = 1").fetchone()
    try:
        favorites = json.loads(row["favorite_recipes"]) if row and row["favorite_recipes"] else []
        if not isinstance(favorites, list):
            favorites = []
    except (json.JSONDecodeError, TypeError):
        favorites = []
    favorites = [f for f in favorites if str(f.get("dish_name", "")).strip().lower() != dish.lower()]
    if rating >= 4:
        favorites.insert(0, {
            "dish_name": dish,
            "rating": rating,
            "rated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        })
    favorites = favorites[:FAVORITE_RECIPES_LIMIT]
    connection.execute("INSERT OR IGNORE INTO user_profile (id) VALUES (1)")
    connection.execute(
        "UPDATE user_profile SET favorite_recipes = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
        (json.dumps(favorites),),
    )


@mcp.tool()
def capture_weekly_menu_rating(menu_item_id: int, kid_rating: int, human_feedback: str = "") -> dict[str, Any]:
    """Capture a human rating from 1 through 5 for a weekly menu item.

    A rating of 4 or 5 also records the dish in the household's top-10 favourite
    recipes (newest first); a lower rating removes it if it was there.
    """
    if not 1 <= kid_rating <= 5:
        raise ValueError("kid_rating must be between 1 and 5")
    with _connect() as connection:
        menu_row = connection.execute("SELECT dish_name FROM weekly_menu WHERE id = ?", (menu_item_id,)).fetchone() 
        if menu_row is None:
            raise ValueError(f"No weekly_menu record found for id {menu_item_id}")
        connection.execute("UPDATE weekly_menu SET kid_rating = ?, human_feedback = ? WHERE id = ?", (kid_rating, human_feedback, menu_item_id))
        _sync_favorite_recipes(connection, menu_row["dish_name"], kid_rating)
    return _record("weekly_menu", menu_item_id)


def _normalize_ingredients_used(ingredients_used: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Validate raw {item_name, quantity, unit} entries into a clean deduction list.

    Keyed by item_name (case-insensitive), matching inventory's own key - never by
    inventory_id, which the caller has no reliable way to know ahead of time."""
    normalized: list[dict[str, Any]] = []
    for item in ingredients_used or []:
        try:
            name = str(item["item_name"]).strip()
            quantity = float(item["quantity"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("each ingredients_used entry requires item_name and numeric quantity") from error
        if not name:
            raise ValueError("each ingredients_used entry requires a non-empty item_name")
        if quantity <= 0:
            raise ValueError("ingredients_used quantities must be greater than zero")
        raw_unit = str(item.get("unit", "")).strip()
        # Tidy a recognized mass/volume/count alias to its canonical short form;
        # leave culinary units (tbsp, cup, ...) and anything unrecognized as
        # given - convert() at deduction time approximates or skips them.
        normalized.append({"item_name": name, "quantity": quantity, "unit": canonicalize_inventory_unit(raw_unit) or raw_unit})
    return normalized


@mcp.tool()
def add_detailed_prep_schedule(
    trigger_day: str,
    trigger_time: str,
    task_type: str,
    detailed_instructions: list[str],
    ingredients_used: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Add a detailed preparation task for a human to execute.

    This is the ONLY place that supplies what the task will consume - there is no
    separate step to add it later, so get_inventory first and fill in ingredients_used
    completely before saving.

    Parameters:
      detailed_instructions: ordered list of short, plain-text instruction steps, e.g.
        ["Dice the onions and tomatoes.", "Heat oil in a wide pan over medium heat.",
         "Add the onions and cook 3 minutes until soft."]
        One step per list entry - do not number them yourself and do not pass a single
        text blob; it must be a JSON array of strings (same convention as weekly_menu's
        full_recipe).
      ingredients_used: every ingredient this task will consume, as a JSON array of
        {item_name, quantity, unit} objects, e.g.
        [{"item_name": "Baby spinach", "quantity": 1, "unit": "pcs"},
         {"item_name": "Greek yogurt", "quantity": 200, "unit": "g"}]
        item_name must match (case-insensitively) an item_name already in inventory -
        copy the exact spelling from get_inventory. The moment a human checks this task
        complete, capture_prep_completion_status looks up each item_name here against
        current inventory and deducts quantity from it automatically, recording an
        inventory_transactions row; an item_name with no matching inventory row is
        skipped rather than failing. Leaving this empty (or omitting an ingredient the
        task genuinely uses) means checking the task off will never touch that stock.
        unit: use grams/kilograms (g, kg), millilitres/litres (ml, l) or pieces
        (pcs). Recipe units - tsp, tbsp, cup - are accepted and approximated to
        g/ml on deduction (1 tsp=5, 1 tbsp=15, 1 cup=240). The quantity is
        converted into the inventory row's own unit before it's deducted, so
        "500 g" against a row tracked in kg deducts 0.5. A unit that can't be
        reconciled with the row's unit (e.g. "2 bags" against a kg row) is
        reported back and left un-deducted rather than applied wrongly - so pick
        a unit in the same dimension (mass/volume/count) as the inventory row.
    """
    instructions = _clean_menu_lines(detailed_instructions, field="detailed_instructions", required=True)
    ingredients = _normalize_ingredients_used(ingredients_used)
    with _connect() as connection:
        cursor = connection.execute(
            "INSERT INTO detailed_prep_schedule (trigger_day, trigger_time, task_type, detailed_instructions, ingredients_used) VALUES (?, ?, ?, ?, ?)",
            (_validate_day(trigger_day), trigger_time.strip(), task_type.strip(), json.dumps(instructions), json.dumps(ingredients)),
        )
    return _record("detailed_prep_schedule", cursor.lastrowid)


@mcp.tool()
def capture_prep_completion_status(prep_schedule_id: int, is_completed: bool, human_notes: str = "") -> dict[str, Any]:
    """Capture whether a human completed a detailed preparation task.

    Checking a task complete (is_completed=True) looks up every {item_name, quantity,
    unit} entry the task was saved with (see add_detailed_prep_schedule) against current
    inventory by item_name (case-insensitive) and deducts quantity from each match
    exactly once, recording an inventory_transactions row - safe to call again with
    is_completed=True on an already-acknowledged task (idempotent no-op, returns the
    task unchanged). An item_name with no matching inventory row is skipped rather than
    failing the whole task. Deductions are never blocked by low stock - a match is
    deducted even if it pushes inventory negative, so the shortfall stays visible until
    a shopping run tops it back up. A task saved with no ingredients_used is just marked
    done and can still be unchecked; once a task WITH ingredients has been deducted it
    is finalized ('acknowledged') and cannot be reopened - a later is_completed=False
    call is rejected.
    """
    with _connect() as connection:
        task = connection.execute("SELECT * FROM detailed_prep_schedule WHERE id = ?", (prep_schedule_id,)).fetchone()
        if task is None:
            raise ValueError(f"No detailed_prep_schedule record found for id {prep_schedule_id}")
        if task["status"] == "cancelled":
            raise ValueError("prep schedule is cancelled")
        if task["status"] == "acknowledged":
            if is_completed:
                return dict(task)  # already finalized - idempotent no-op
            raise ValueError("prep schedule ingredients were already deducted and cannot be reopened")

        if not is_completed:
            connection.execute(
                "UPDATE detailed_prep_schedule SET is_completed = 0, status = 'proposed', human_notes = ? WHERE id = ?",
                (human_notes, prep_schedule_id),
            )
            return _record_in_connection(connection, "detailed_prep_schedule", prep_schedule_id)

        ingredients = json.loads(task["ingredients_used"] or "[]")

        if not ingredients:
            # Nothing to deduct - mark done without the "ingredients already deducted"
            # lock, so a plain task (e.g. "Wipe counters") can still be unchecked.
            connection.execute(
                "UPDATE detailed_prep_schedule SET is_completed = 1, status = 'completed', human_notes = ? WHERE id = ?",
                (human_notes, prep_schedule_id),
            )
            return _record_in_connection(connection, "detailed_prep_schedule", prep_schedule_id)

        acknowledgement_key = f"prep-{prep_schedule_id}-complete"

        # Prep deductions are never blocked by low stock: the household cooked with what
        # it physically had, even if our tracked number lagged. Present items are
        # deducted and allowed to go negative, so the shortfall stays visible until a
        # shopping run tops it back up; an item_name with no matching inventory row is
        # simply skipped rather than failing the acknowledgement.
        # Each entry's quantity is converted into the matched row's stored unit
        # first (units.convert): "500 g" against a "kg" row deducts 0.5. A line
        # whose unit can't be reconciled with the row's (different dimension, or
        # an unrecognized unit) is skipped and reported in conversion_warnings
        # rather than applied as a wrong number.
        conversion_warnings: list[str] = []
        for index, entry in enumerate(ingredients):
            inventory = connection.execute("SELECT * FROM inventory WHERE item_name = ?", (entry["item_name"],)).fetchone()
            if inventory is None:
                continue
            amount, note, ok = convert(entry["quantity"], entry.get("unit"), inventory["unit"])
            if not ok or amount <= 0:
                conversion_warnings.append(
                    f"{entry['item_name']}: {note or 'quantity resolves to zero'}; not deducted"
                )
                continue
            before = inventory["quantity"]
            after = round(before - amount, 4)
            reason = "Prep acknowledged" + (f" ({note})" if note else "")
            connection.execute("UPDATE inventory SET quantity = ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?", (after, inventory["id"]))
            connection.execute(
                "INSERT INTO inventory_transactions (inventory_id, quantity_change, quantity_before, quantity_after, reason, source_type, source_id, idempotency_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (inventory["id"], -amount, before, after, reason, "prep_schedule", prep_schedule_id, f"{acknowledgement_key}:{index}"),
            )
        connection.execute(
            "UPDATE detailed_prep_schedule SET is_completed = 1, status = 'acknowledged', acknowledgement_key = ?, human_notes = ? WHERE id = ?",
            (acknowledgement_key, human_notes, prep_schedule_id),
        )
        result = _record_in_connection(connection, "detailed_prep_schedule", prep_schedule_id)
        if conversion_warnings:
            result["conversion_warnings"] = conversion_warnings
        return result


def cancel_prep_schedule(prep_schedule_id: int, human_notes: str = "") -> dict[str, Any]:
    """Soft-cancel a prep task: it drops out of every schedule/dashboard view but the
    row (and any history) is kept. A task whose ingredients were already deducted
    cannot be cancelled."""
    with _connect() as connection:
        task = connection.execute("SELECT * FROM detailed_prep_schedule WHERE id = ?", (prep_schedule_id,)).fetchone()
        if task is None:
            raise ValueError(f"No detailed_prep_schedule record found for id {prep_schedule_id}")
        if task["status"] == "acknowledged":
            raise ValueError("cannot cancel a task whose ingredients were already deducted")
        connection.execute(
            "UPDATE detailed_prep_schedule SET status = 'cancelled', is_completed = 0, human_notes = ? WHERE id = ?",
            (human_notes or task["human_notes"], prep_schedule_id),
        )
    return _record("detailed_prep_schedule", prep_schedule_id)


def _record_in_connection(connection: sqlite3.Connection, table: str, record_id: int) -> dict[str, Any]:
    row = connection.execute(f"SELECT * FROM {table} WHERE id = ?", (record_id,)).fetchone()
    return dict(row) if row is not None else {}


@mcp.tool()
def add_shopping_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add ingredients to the one pending shopping list, merging into whatever is
    already there - never touches inventory.

    This is an upsert keyed on item_name (case-insensitive): call it any time something
    is newly needed, whether or not a list already exists. If an item with the same name
    is already pending, its proposed_quantity is increased by the amount given here (and
    its unit is overwritten to whatever this call passes) instead of creating a second
    row - there is no separate "create" vs "append" choice to make, and no need to call
    get_shopping_items first just to decide that. Never propose an item_name that's
    already pending unless you actually want to add more of it.

    Each entry is {item_name, proposed_quantity, unit}. Returns the current state of
    every item this call touched. See acknowledge_shopping_items to record an actual
    purchase and move quantities into inventory.
    """
    if not items:
        raise ValueError("items must contain at least one item")
    with _connect() as connection:
        touched_names = []
        for item in items:
            try:
                name, quantity, unit = str(item["item_name"]).strip(), float(item["proposed_quantity"]), str(item["unit"]).strip()
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("each shopping item requires item_name, proposed_quantity, and unit") from error
            if not name or quantity <= 0 or not unit:
                raise ValueError("shopping item names, quantities, and units must be valid")
            unit = canonicalize_inventory_unit(unit) or unit  # tidy "grams"->"g" etc; leave the rest
            connection.execute(
                """
                INSERT INTO shopping_items (item_name, proposed_quantity, unit) VALUES (?, ?, ?)
                ON CONFLICT(item_name) DO UPDATE SET
                    proposed_quantity = proposed_quantity + excluded.proposed_quantity,
                    unit = excluded.unit,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (name, quantity, unit),
            )
            touched_names.append(name)
        placeholders = ",".join("?" * len(touched_names))
        return [dict(row) for row in connection.execute(
            f"SELECT * FROM shopping_items WHERE item_name IN ({placeholders}) ORDER BY item_name", touched_names,
        )]


@mcp.tool()
def edit_shopping_item(shopping_item_id: int, proposed_quantity: float | None = None, unit: str | None = None) -> dict[str, Any]:
    """Correct a pending shopping item's quantity and/or unit in place. Pass whichever of
    proposed_quantity/unit changed; the other is left as-is."""
    if proposed_quantity is None and unit is None:
        raise ValueError("provide proposed_quantity and/or unit to change")
    if proposed_quantity is not None and proposed_quantity <= 0:
        raise ValueError("proposed_quantity must be greater than zero")
    with _connect() as connection:
        row = connection.execute("SELECT * FROM shopping_items WHERE id = ?", (shopping_item_id,)).fetchone()
        if row is None:
            raise ValueError(f"No shopping item found for id {shopping_item_id}")
        new_unit = row["unit"]
        if unit:
            new_unit = canonicalize_inventory_unit(unit) or unit.strip()
        connection.execute(
            "UPDATE shopping_items SET proposed_quantity = ?, unit = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (proposed_quantity if proposed_quantity is not None else row["proposed_quantity"],
             new_unit, shopping_item_id),
        )
    return _record("shopping_items", shopping_item_id)


@mcp.tool()
def delete_shopping_item(shopping_item_id: int) -> dict[str, Any]:
    """Remove one pending item from the shopping list without buying it (e.g. it's no
    longer needed, or it was a mistaken suggestion). Returns the row as it was."""
    with _connect() as connection:
        row = connection.execute("SELECT * FROM shopping_items WHERE id = ?", (shopping_item_id,)).fetchone()
        if row is None:
            raise ValueError(f"No shopping item found for id {shopping_item_id}")
        connection.execute("DELETE FROM shopping_items WHERE id = ?", (shopping_item_id,))
    return dict(row)


@mcp.tool()
def clear_shopping_items() -> dict[str, Any]:
    """Remove every pending shopping item without buying any of them (start the list
    over from empty). Returns how many rows were cleared."""
    with _connect() as connection:
        count = connection.execute("SELECT COUNT(*) FROM shopping_items").fetchone()[0]
        connection.execute("DELETE FROM shopping_items")
    return {"cleared": count}


def acknowledge_shopping_items(acknowledgement_key: str, purchased_items: list[dict[str, Any]]) -> dict[str, Any]:
    """Move purchased quantities into inventory and clear those items off the pending
    shopping list, each exactly once.

    purchased_items is [{shopping_item_id, actual_quantity}]. actual_quantity is read
    in the shopping item's own unit and converted into the matched inventory row's
    stored unit before it's added (buying "2 kg" of a row tracked in "g" adds 2000).
    Inventory is matched (and created if it doesn't exist yet) by the shopping item's
    item_name - never by inventory_id, since that's an internal id the caller shouldn't
    need to track. Once applied, the shopping_items row is deleted (this is what
    "clears" it off the list); a replay with the same acknowledgement_key (e.g. a
    retried request) is a safe no-op that will not double-add stock, even though by
    then the row it originally matched is already gone. An item whose unit can't be
    reconciled with the existing inventory row's unit is left on the list and reported
    in "warnings" instead of being added with a wrong number.
    """
    if not acknowledgement_key.strip() or not purchased_items:
        raise ValueError("acknowledgement_key and purchased_items are required")
    normalized_purchases = []
    for item in purchased_items:
        try:
            item_id = int(item["shopping_item_id"])
            quantity = float(item["actual_quantity"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("each purchased item requires shopping_item_id and a numeric actual_quantity") from error
        if quantity < 0:
            raise ValueError("actual quantities cannot be negative")
        normalized_purchases.append((item_id, quantity))

    with _connect() as connection:
        applied_ids: list[int] = []
        already_applied_ids: list[int] = []
        warnings: list[str] = []
        for item_id, quantity in normalized_purchases:
            idempotency_key = f"{acknowledgement_key}:{item_id}"
            if connection.execute("SELECT 1 FROM inventory_transactions WHERE idempotency_key = ?", (idempotency_key,)).fetchone():
                already_applied_ids.append(item_id)
                continue
            row = connection.execute("SELECT * FROM shopping_items WHERE id = ?", (item_id,)).fetchone()
            if row is None:
                # Already cleared under a different acknowledgement_key (or never
                # existed) - nothing left here to apply.
                continue
            if quantity > 0:
                inventory = connection.execute("SELECT * FROM inventory WHERE item_name = ?", (row["item_name"],)).fetchone()
                if inventory is None:
                    # New row: store it in the canonical form of the shopping
                    # unit when we recognize one, else take the unit as typed.
                    new_unit = canonicalize_inventory_unit(row["unit"]) or row["unit"]
                    cursor = connection.execute("INSERT INTO inventory (item_name, category, quantity, unit) VALUES (?, 'Pantry', ?, ?)", (row["item_name"], quantity, new_unit))
                    inventory_id, before, added, note = cursor.lastrowid, 0, quantity, ""
                else:
                    added, note, ok = convert(quantity, row["unit"], inventory["unit"])
                    if not ok or added <= 0:
                        warnings.append(
                            f"{row['item_name']}: {note or 'quantity resolves to zero'}; left on the shopping list"
                        )
                        continue
                    inventory_id, before = inventory["id"], inventory["quantity"]
                    connection.execute("UPDATE inventory SET quantity = quantity + ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?", (added, inventory_id))
                reason = "Shopping purchase acknowledged" + (f" ({note})" if note else "")
                connection.execute(
                    "INSERT INTO inventory_transactions (inventory_id, quantity_change, quantity_before, quantity_after, reason, source_type, source_id, idempotency_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (inventory_id, added, before, round(before + added, 4), reason, "shopping_item", item_id, idempotency_key),
                )
            connection.execute("DELETE FROM shopping_items WHERE id = ?", (item_id,))
            applied_ids.append(item_id)
        replayed = not applied_ids and bool(already_applied_ids)
        result: dict[str, Any] = {"replayed": replayed, "cleared_item_ids": applied_ids}
        if warnings:
            result["warnings"] = warnings
        return result


def get_user_profile() -> dict[str, Any]:
    """Read the single household profile row (name, contact email, preferences)."""
    with _connect() as connection:
        row = connection.execute("SELECT * FROM user_profile WHERE id = 1").fetchone()
    return dict(row) if row is not None else {}


def update_user_profile(
    name: str | None = None,
    email: str | None = None,
    cc_emails: str | None = None,
    notes: str | None = None,
    notify_on_task_creation: bool | None = None,
) -> dict[str, Any]:
    """Patch the household profile. Only the fields passed (non-None) are changed.

    `cc_emails` is a free-form string of extra addresses (comma/semicolon/newline
    separated) copied on task-alert emails. `favorite_recipes` is not patchable here -
    it's maintained automatically from weekly-menu ratings.
    """
    if email is not None and email.strip() and "@" not in email:
        raise ValueError("email must be a valid address")
    assignments: list[str] = []
    values: list[Any] = []
    for column, value in (("name", name), ("email", email), ("cc_emails", cc_emails), ("notes", notes)):
        if value is not None:
            assignments.append(f"{column} = ?")
            values.append(str(value).strip())
    if notify_on_task_creation is not None:
        assignments.append("notify_on_task_creation = ?")
        values.append(int(bool(notify_on_task_creation)))
    if not assignments:
        return get_user_profile()
    with _connect() as connection:
        connection.execute("INSERT OR IGNORE INTO user_profile (id) VALUES (1)")
        connection.execute(
            f"UPDATE user_profile SET {', '.join(assignments)}, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
            values,
        )
    return get_user_profile()


@mcp.tool()
def get_household_preferences() -> dict[str, Any]:
    """Planning context set by the household on the profile screen.

    Returns the chef's free-text note and the household's most recently top-rated
    dishes (up to 10, newest first, each with its star rating and when it was rated).
    Consult this before building or revising the weekly menu so the plan leans on
    dishes the family actually enjoyed lately - repeat or riff on them wherever the
    dietary rules allow.
    """
    profile = get_user_profile()
    try:
        favorites = json.loads(profile.get("favorite_recipes") or "[]")
        if not isinstance(favorites, list):
            favorites = []
    except (json.JSONDecodeError, TypeError):
        favorites = []
    chef_note = profile.get("notes", "") or ""
    favorite_recipes = [
        {
            "dish_name": entry.get("dish_name", ""),
            "rating": entry.get("rating"),
            "rated_at": entry.get("rated_at"),
        }
        for entry in favorites
        if entry.get("dish_name")
    ]
    if favorite_recipes or chef_note.strip():
        guidance = "Weight these favourites and the note when planning, within the dietary rules."
    else:
        guidance = (
            "No saved favourites or chef note yet - this is optional context, not a blocker. "
            "Plan the week from current inventory, the dietary and macro rules, and everyday variety."
        )
    return {
        "chef_note": chef_note,
        "favorite_recipes": favorite_recipes,
        "has_preferences": bool(favorite_recipes or chef_note.strip()),
        "guidance": guidance,
    }


# --- Email notifications: moved out of dbmcp --------------------------------------
# The three send_*_email tools, their Pydantic payload models, the SMTP transport and
# the body builders now live in agents/app/email/ (schemas / smtp /
# render / backfill / tools). The agent is the only process that sends mail, and none
# of it needed the database directly - it back-fills the saved menu / shopping items
# over the dbmcp REST API instead. dbmcp keeps no SMTP config.


class InventoryAddRequest(BaseModel):
    item_name: str = Field(min_length=1)
    quantity: float = Field(ge=0)
    unit: str = Field(min_length=1)
    category: str = "Pantry"
    minimum_threshold: float = Field(default=0, ge=0)


class InventoryAdjustmentRequest(BaseModel):
    quantity_change: float


class InventoryDiscardRequest(BaseModel):
    quantity: float = Field(gt=0)
    reason: str = "Discarded"


class MenuItemRequest(BaseModel):
    day_of_week: str
    meal_type: str = Field(min_length=1)
    dish_name: str = Field(min_length=1)
    is_kid_friendly: bool
    macros: str
    ingredients: list[str] = Field(min_length=1)
    full_recipe: list[str] = Field(default_factory=list)

    @field_validator("day_of_week")
    @classmethod
    def validate_day(cls, value: str) -> str:
        return _validate_day(value)


class MenuRatingRequest(BaseModel):
    kid_rating: int = Field(ge=1, le=5)
    human_feedback: str = ""


class PrepScheduleRequest(BaseModel):
    trigger_day: str
    trigger_time: str = Field(min_length=1)
    task_type: str = Field(min_length=1)
    detailed_instructions: list[str] = Field(min_length=1)
    ingredients_used: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("trigger_day")
    @classmethod
    def validate_day(cls, value: str) -> str:
        return _validate_day(value)


class PrepCompletionRequest(BaseModel):
    is_completed: bool
    human_notes: str = ""


class PrepCancellationRequest(BaseModel):
    human_notes: str = ""


class ShoppingItemRequest(BaseModel):
    item_name: str = Field(min_length=1)
    proposed_quantity: float = Field(gt=0)
    unit: str = Field(min_length=1)


class ShoppingItemsRequest(BaseModel):
    items: list[ShoppingItemRequest] = Field(min_length=1)


class ShoppingItemEditRequest(BaseModel):
    proposed_quantity: float | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, min_length=1)


class ShoppingAcknowledgementRequest(BaseModel):
    acknowledgement_key: str = Field(min_length=1, max_length=200)
    purchased_items: list[dict[str, Any]] = Field(min_length=1)


class AgentRunRequest(BaseModel):
    agent_role: str = Field(min_length=1, max_length=80)
    job_name: str = Field(min_length=1, max_length=80)
    status: str = Field(pattern="^(completed|failed)$")
    result: str = ""
    error: str = ""


# --- soft-deleted: no caller --------------------------------------------------
# MenuPolicyRequest / MenuPlanRequest backed POST /api/weekly-menu/validate and
# POST /api/weekly-menu/plan, neither of which anything calls. The
# validate_weekly_menu_policy MCP tool (used by the weekly_menu job) stays.
#
# class MenuPolicyRequest(BaseModel):
#     menu_items: list[dict[str, Any]] = Field(min_length=1)
#
# class MenuPlanRequest(BaseModel):
#     menu_items: list[dict[str, Any]] = Field(min_length=5)


class ChatSessionRequest(BaseModel):
    messages: list[dict[str, Any]]


class ProfileUpdateRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    cc_emails: str | None = None
    notes: str | None = None
    notify_on_task_creation: bool | None = None


def _tool_error(error: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(error))


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not os.environ.get("KITCHENHQ_API_KEY"):
        raise RuntimeError("KITCHENHQ_API_KEY must be set")
    initialize_database()
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="KitchenHQ Database Tools", lifespan=lifespan)


@app.middleware("http")
async def require_api_key(request: Request, call_next):
    if request.url.path not in PUBLIC_PATHS and request.headers.get(API_KEY_HEADER) != os.environ.get("KITCHENHQ_API_KEY"):
        return JSONResponse({"detail": "Invalid or missing API key"}, status_code=401)
    return await call_next(request)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ready"}


@app.get("/api/dashboard")
def dashboard() -> dict[str, Any]:
    with _connect() as connection:
        return {
            "inventory": [dict(row) for row in connection.execute("SELECT * FROM inventory ORDER BY category, item_name")],
            "menu": [dict(row) for row in connection.execute("SELECT * FROM weekly_menu ORDER BY CASE day_of_week WHEN 'monday' THEN 1 WHEN 'tuesday' THEN 2 WHEN 'wednesday' THEN 3 WHEN 'thursday' THEN 4 WHEN 'friday' THEN 5 WHEN 'saturday' THEN 6 WHEN 'sunday' THEN 7 ELSE 8 END, CASE meal_type WHEN 'breakfast' THEN 1 WHEN 'lunch' THEN 2 WHEN 'snack' THEN 3 WHEN 'dinner' THEN 4 ELSE 5 END, id")],
            "tasks": [dict(row) for row in connection.execute("SELECT * FROM detailed_prep_schedule WHERE status <> 'cancelled' AND (is_completed = 0 OR id IN (SELECT id FROM detailed_prep_schedule WHERE is_completed = 1 AND status <> 'cancelled' ORDER BY id DESC LIMIT 10)) ORDER BY is_completed, id")],
            "shopping_items": [dict(row) for row in connection.execute("SELECT * FROM shopping_items ORDER BY item_name")],
            "consumption": [dict(row) for row in connection.execute(
                """
                SELECT i.id AS inventory_id, i.item_name, i.unit,
                       ROUND(SUM(-t.quantity_change), 3) AS quantity_consumed,
                       COUNT(*) AS transaction_count,
                       MAX(t.created_at) AS last_consumed_at
                FROM inventory_transactions t
                JOIN inventory i ON i.id = t.inventory_id
                WHERE t.quantity_change < 0
                  AND t.created_at >= datetime('now', '-7 days')
                GROUP BY t.inventory_id
                ORDER BY quantity_consumed DESC, i.item_name
                """
            )],
            "profile": (lambda row: dict(row) if row is not None else {})(
                connection.execute("SELECT * FROM user_profile WHERE id = 1").fetchone()
            ),
        }


@app.post("/api/inventory")
def api_add_inventory(request: InventoryAddRequest) -> dict[str, Any]:
    try:
        return add_inventory(**request.model_dump())
    except ValueError as error:
        raise _tool_error(error) from error


@app.patch("/api/inventory/{item_id}")
def api_adjust_inventory(item_id: int, request: InventoryAdjustmentRequest) -> dict[str, Any]:
    try:
        return adjust_inventory_quantity(item_id, request.quantity_change)
    except ValueError as error:
        raise _tool_error(error) from error


@app.post("/api/inventory/{item_id}/discard")
def api_discard_inventory(item_id: int, request: InventoryDiscardRequest) -> dict[str, Any]:
    try:
        return remove_or_discard_inventory(item_id, **request.model_dump())
    except ValueError as error:
        raise _tool_error(error) from error


@app.post("/api/weekly-menu")
def api_add_menu_item(request: MenuItemRequest) -> dict[str, Any]:
    try:
        return add_weekly_menu_item(**request.model_dump())
    except ValueError as error:
        raise _tool_error(error) from error


@app.post("/api/weekly-menu/{menu_item_id}/rating")
def api_capture_rating(menu_item_id: int, request: MenuRatingRequest) -> dict[str, Any]:
    try:
        return capture_weekly_menu_rating(menu_item_id, **request.model_dump())
    except ValueError as error:
        raise _tool_error(error) from error


@app.post("/api/prep-schedule")
def api_add_prep_schedule(request: PrepScheduleRequest) -> dict[str, Any]:
    try:
        return add_detailed_prep_schedule(**request.model_dump())
    except ValueError as error:
        raise _tool_error(error) from error


@app.patch("/api/prep-schedule/{prep_schedule_id}/completion")
def api_capture_completion(prep_schedule_id: int, request: PrepCompletionRequest) -> dict[str, Any]:
    try:
        return capture_prep_completion_status(prep_schedule_id, **request.model_dump())
    except ValueError as error:
        raise _tool_error(error) from error


@app.post("/api/prep-schedule/{prep_schedule_id}/cancel")
def api_cancel_prep(prep_schedule_id: int, request: PrepCancellationRequest) -> dict[str, Any]:
    try:
        return cancel_prep_schedule(prep_schedule_id, **request.model_dump())
    except ValueError as error:
        raise _tool_error(error) from error


@app.get("/api/shopping-items")
def api_get_shopping_items() -> list[dict[str, Any]]:
    return get_shopping_items()


@app.post("/api/shopping-items")
def api_add_shopping_items(request: ShoppingItemsRequest) -> list[dict[str, Any]]:
    try:
        return add_shopping_items([item.model_dump() for item in request.items])
    except ValueError as error:
        raise _tool_error(error) from error


@app.patch("/api/shopping-items/{shopping_item_id}")
def api_edit_shopping_item(shopping_item_id: int, request: ShoppingItemEditRequest) -> dict[str, Any]:
    try:
        return edit_shopping_item(shopping_item_id, **request.model_dump())
    except ValueError as error:
        raise _tool_error(error) from error


@app.delete("/api/shopping-items/{shopping_item_id}")
def api_delete_shopping_item(shopping_item_id: int) -> dict[str, Any]:
    try:
        return delete_shopping_item(shopping_item_id)
    except ValueError as error:
        raise _tool_error(error) from error


@app.post("/api/shopping-items/clear")
def api_clear_shopping_items() -> dict[str, Any]:
    return clear_shopping_items()


@app.post("/api/shopping-items/acknowledge")
def api_acknowledge_shopping(request: ShoppingAcknowledgementRequest) -> dict[str, Any]:
    try:
        return acknowledge_shopping_items(**request.model_dump())
    except ValueError as error:
        raise _tool_error(error) from error


@app.post("/api/agent-runs")
def api_record_agent_run(request: AgentRunRequest) -> dict[str, Any]:
    with _connect() as connection:
        cursor = connection.execute(
            "INSERT INTO agent_runs (agent_role, job_name, status, result, error) VALUES (?, ?, ?, ?, ?)",
            (request.agent_role, request.job_name, request.status, request.result, request.error),
        )
        return _record_in_connection(connection, "agent_runs", cursor.lastrowid)


@app.get("/api/agent-runs")
def api_agent_runs() -> list[dict[str, Any]]:
    with _connect() as connection:
        return [dict(row) for row in connection.execute("SELECT * FROM agent_runs ORDER BY id DESC LIMIT 100")]


# --- soft-deleted: no caller --------------------------------------------------
# Nothing calls POST /api/weekly-menu/validate or POST /api/weekly-menu/plan
# (chatui has no proxy for either; the agent works slot-by-slot over MCP).
#
# @app.post("/api/weekly-menu/validate")
# def api_validate_menu(request: MenuPolicyRequest) -> dict[str, Any]:
#     return validate_weekly_menu_policy(request.menu_items)
#
# @app.post("/api/weekly-menu/plan")
# def api_add_menu_plan(request: MenuPlanRequest) -> dict[str, Any]:
#     try:
#         return add_weekly_menu_plan(request.menu_items)
#     except ValueError as error:
#         raise _tool_error(error) from error


@app.get("/api/profile")
def api_get_profile() -> dict[str, Any]:
    return get_user_profile()


@app.put("/api/profile")
def api_update_profile(request: ProfileUpdateRequest) -> dict[str, Any]:
    try:
        return update_user_profile(**request.model_dump())
    except ValueError as error:
        raise _tool_error(error) from error


# Email notification routes removed - see agents/app/email/. The agent
# sends prep-plan / weekly-menu / shopping-list mail itself via local tools.


@app.get("/api/chat-sessions")
def api_list_chat_sessions(limit: int = 5) -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT session_id, messages_json, updated_at FROM chat_sessions ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    sessions = []
    for row in rows:
        messages = json.loads(row["messages_json"])
        preview = next(
            (message.get("data", {}).get("content", "") for message in messages if message.get("type") == "human"),
            "",
        )
        sessions.append({"session_id": row["session_id"], "updated_at": row["updated_at"], "preview": preview[:120]})
    return sessions


@app.get("/api/chat-sessions/{session_id}")
def api_get_chat_session(session_id: str) -> dict[str, Any]:
    with _connect() as connection:
        row = connection.execute("SELECT messages_json FROM chat_sessions WHERE session_id = ?", (session_id,)).fetchone()
    return {"messages": json.loads(row["messages_json"]) if row else []}


@app.put("/api/chat-sessions/{session_id}")
def api_put_chat_session(session_id: str, request: ChatSessionRequest) -> dict[str, Any]:
    with _connect() as connection:
        connection.execute(
            "INSERT INTO chat_sessions (session_id, messages_json, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(session_id) DO UPDATE SET messages_json = excluded.messages_json, updated_at = CURRENT_TIMESTAMP",
            (session_id, json.dumps(request.messages)),
        )
    return {"session_id": session_id, "messages": request.messages}


app.mount("/", mcp.streamable_http_app())


if __name__ == "__main__":
    import uvicorn

    initialize_database()
    uvicorn.run(app, host=os.environ.get("MCP_HOST", "0.0.0.0"), port=int(os.environ.get("MCP_PORT", "18000")))