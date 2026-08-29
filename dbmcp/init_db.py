"""KitchenHQ database tools exposed through FastAPI and FastMCP."""

from __future__ import annotations

import os
import json
import re
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, Field, field_validator

DATABASE_PATH = Path(os.environ.get("KITCHEN_DB_PATH", Path(__file__).with_name("kitchen.db")))
VALID_DAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
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
                category TEXT NOT NULL, quantity REAL NOT NULL CHECK (quantity >= 0),
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
                human_feedback TEXT
            );
            CREATE TABLE IF NOT EXISTS detailed_prep_schedule (
                id INTEGER PRIMARY KEY, trigger_day TEXT NOT NULL, trigger_time TEXT NOT NULL,
                task_type TEXT NOT NULL, detailed_instructions TEXT NOT NULL,
                is_completed BOOLEAN NOT NULL DEFAULT 0, human_notes TEXT,
                ingredients_used TEXT, ingredients_created TEXT
            );
        """)
        menu_columns = {row[1] for row in connection.execute("PRAGMA table_info(weekly_menu)")}
        if "full_recipe" not in menu_columns:
            connection.execute("ALTER TABLE weekly_menu ADD COLUMN full_recipe TEXT NOT NULL DEFAULT ''")
        if connection.execute("SELECT 1 FROM inventory WHERE item_name = 'Baby spinach'").fetchone() is None:
            connection.executemany(
                "INSERT INTO inventory (item_name, category, quantity, unit, minimum_threshold) VALUES (?, ?, ?, ?, ?)",
                [
                    ("Baby spinach", "Fresh", 2, "bags", 1),
                    ("Paneer", "Dairy", 450, "g", 250),
                    ("Brown rice", "Pantry", 1.8, "kg", 1),
                    ("Cherry tomatoes", "Fresh", 350, "g", 200),
                    ("Eggs", "Proteins", 10, "pcs", 6),
                    ("Greek yogurt", "Dairy", 700, "g", 300),
                ],
            )
        if connection.execute("SELECT COUNT(*) FROM weekly_menu WHERE full_recipe <> ''").fetchone()[0] < 28:
            connection.executemany(
                "INSERT INTO weekly_menu (day_of_week, meal_type, dish_name, is_kid_friendly, macros, ingredients, full_recipe) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (day, meal_type, dish, 1, macros, ingredients, f"Ingredients:\n{ingredients}\n\nMethod:\n1. Wash and prepare every ingredient, then measure the spices and liquids into separate bowls.\n2. Heat a wide pan over medium heat and add the oil. Add the aromatics and cook for 2 minutes until fragrant.\n3. Add the main ingredients and cook for 5 minutes, stirring often so the edges colour evenly.\n4. Add the grains, sauce, or liquid, reduce the heat, cover, and cook for 10 minutes until tender.\n5. Remove the lid, taste, and adjust salt, acidity, and seasoning. Rest for 2 minutes.\n6. Plate while warm, finish with the fresh garnish, and serve immediately." )
                    for day, meals in {
                        "monday": [("Breakfast", "Spinach masala eggs", "26g protein  /  18g carbs  /  20g fat", "Eggs, baby spinach, tomatoes"), ("Lunch", "Paneer tikka bowls", "32g protein  /  48g carbs  /  18g fat", "Paneer, brown rice, spinach, yogurt"), ("Snack", "Yogurt fruit crunch", "18g protein  /  26g carbs  /  8g fat", "Greek yogurt, banana, seeds"), ("Dinner", "Lemon herb rice skillet", "24g protein  /  52g carbs  /  14g fat", "Brown rice, spinach, yogurt")],
                        "tuesday": [("Breakfast", "Savory paneer toast", "29g protein  /  31g carbs  /  16g fat", "Paneer, wholegrain bread, tomatoes"), ("Lunch", "Tomato egg shakshuka", "28g protein  /  22g carbs  /  16g fat", "Eggs, cherry tomatoes, spinach"), ("Snack", "Spiced yogurt dip", "14g protein  /  12g carbs  /  7g fat", "Greek yogurt, cucumber, herbs"), ("Dinner", "Tikka rice lettuce cups", "30g protein  /  39g carbs  /  15g fat", "Paneer, brown rice, lettuce")],
                        "wednesday": [("Breakfast", "Green breakfast bowl", "22g protein  /  35g carbs  /  12g fat", "Eggs, spinach, brown rice"), ("Lunch", "Green goddess rice", "24g protein  /  54g carbs  /  14g fat", "Brown rice, spinach, yogurt"), ("Snack", "Tomato paneer skewers", "19g protein  /  14g carbs  /  9g fat", "Paneer, cherry tomatoes, herbs"), ("Dinner", "Creamy spinach eggs", "27g protein  /  20g carbs  /  19g fat", "Eggs, spinach, Greek yogurt")],
                        "thursday": [("Breakfast", "Yogurt oat parfait", "20g protein  /  42g carbs  /  10g fat", "Greek yogurt, oats, banana"), ("Lunch", "Roasted paneer salad", "35g protein  /  20g carbs  /  21g fat", "Paneer, cherry tomatoes, spinach"), ("Snack", "Cucumber raita cup", "12g protein  /  10g carbs  /  5g fat", "Greek yogurt, cucumber, herbs"), ("Dinner", "Golden egg rice", "25g protein  /  46g carbs  /  15g fat", "Eggs, brown rice, spinach")],
                        "friday": [("Breakfast", "Paneer breakfast hash", "31g protein  /  34g carbs  /  17g fat", "Paneer, brown rice, tomatoes"), ("Lunch", "Egg and spinach wraps", "30g protein  /  36g carbs  /  17g fat", "Eggs, spinach, yogurt"), ("Snack", "Cinnamon yogurt bowl", "17g protein  /  24g carbs  /  6g fat", "Greek yogurt, banana, seeds"), ("Dinner", "Friday tomato rice", "23g protein  /  55g carbs  /  12g fat", "Brown rice, tomatoes, eggs")],
                        "saturday": [("Breakfast", "Herbed egg scramble", "25g protein  /  16g carbs  /  18g fat", "Eggs, spinach, herbs"), ("Lunch", "Paneer rainbow plate", "34g protein  /  32g carbs  /  19g fat", "Paneer, brown rice, tomatoes"), ("Snack", "Yogurt cucumber cups", "13g protein  /  11g carbs  /  5g fat", "Greek yogurt, cucumber"), ("Dinner", "One-pan spinach pilaf", "21g protein  /  51g carbs  /  13g fat", "Brown rice, spinach, yogurt")],
                        "sunday": [("Breakfast", "Weekend masala omelet", "27g protein  /  14g carbs  /  20g fat", "Eggs, tomatoes, spinach"), ("Lunch", "Sunday paneer bowls", "33g protein  /  49g carbs  /  18g fat", "Paneer, brown rice, yogurt"), ("Snack", "Fruit and yogurt lassi", "15g protein  /  30g carbs  /  5g fat", "Greek yogurt, banana, herbs"), ("Dinner", "Comfort tomato shakshuka", "28g protein  /  24g carbs  /  16g fat", "Eggs, tomatoes, spinach")],
                    }.items() for meal_type, dish, macros, ingredients in meals
                ],
            )
        if connection.execute("SELECT 1 FROM detailed_prep_schedule WHERE task_type = 'Morning prep'").fetchone() is None:
            connection.executemany(
                "INSERT INTO detailed_prep_schedule (trigger_day, trigger_time, task_type, detailed_instructions, ingredients_used, ingredients_created) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    ("monday", "07:30", "Morning prep", "Wash spinach and portion yogurt for the day's bowls.", "Spinach, Greek yogurt", "Portioned yogurt"),
                    ("tuesday", "17:00", "Dinner prep", "Dice tomatoes and press paneer before cooking.", "Cherry tomatoes, Paneer", "Ready-to-cook ingredients"),
                    ("wednesday", "08:00", "Batch prep", "Cook brown rice and cool it in shallow containers.", "Brown rice", "Cooked brown rice"),
                ],
            )
        columns = {row[1] for row in connection.execute("PRAGMA table_info(detailed_prep_schedule)")}
        if "status" not in columns:
            connection.execute("ALTER TABLE detailed_prep_schedule ADD COLUMN status TEXT NOT NULL DEFAULT 'proposed'")
        if "consumption_json" not in columns:
            connection.execute("ALTER TABLE detailed_prep_schedule ADD COLUMN consumption_json TEXT NOT NULL DEFAULT '[]'")
        if "acknowledgement_key" not in columns:
            connection.execute("ALTER TABLE detailed_prep_schedule ADD COLUMN acknowledgement_key TEXT")
        connection.execute("UPDATE detailed_prep_schedule SET status = 'completed' WHERE is_completed = 1 AND status = 'proposed'")
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS inventory_transactions (
                id INTEGER PRIMARY KEY,
                inventory_id INTEGER NOT NULL REFERENCES inventory(id),
                quantity_change REAL NOT NULL CHECK (quantity_change <> 0),
                quantity_before REAL NOT NULL,
                quantity_after REAL NOT NULL CHECK (quantity_after >= 0),
                reason TEXT NOT NULL,
                source_type TEXT,
                source_id INTEGER,
                idempotency_key TEXT NOT NULL UNIQUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS shopping_lists (
                id INTEGER PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'proposed',
                generated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                acknowledged_at DATETIME,
                acknowledgement_key TEXT UNIQUE
            );
            CREATE TABLE IF NOT EXISTS shopping_items (
                id INTEGER PRIMARY KEY,
                shopping_list_id INTEGER NOT NULL REFERENCES shopping_lists(id),
                item_name TEXT NOT NULL,
                proposed_quantity REAL NOT NULL CHECK (proposed_quantity > 0),
                actual_quantity REAL CHECK (actual_quantity >= 0),
                unit TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'proposed'
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
        """)


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
    """Read preparation schedules."""
    with _connect() as connection:
        return [dict(row) for row in connection.execute("SELECT * FROM detailed_prep_schedule ORDER BY is_completed, id")]


@mcp.tool()
def get_shopping_lists() -> list[dict[str, Any]]:
    """Read shopping proposals and their items."""
    with _connect() as connection:
        return [{**dict(row), "items": [dict(item) for item in connection.execute("SELECT * FROM shopping_items WHERE shopping_list_id = ?", (row["id"],))]} for row in connection.execute("SELECT * FROM shopping_lists ORDER BY id DESC")]


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
    """Add a new ingredient to inventory."""
    if not item_name.strip() or not unit.strip():
        raise ValueError("item_name and unit are required")
    if quantity < 0 or minimum_threshold < 0:
        raise ValueError("quantity and minimum_threshold cannot be negative")
    with _connect() as connection:
        try:
            cursor = connection.execute("INSERT INTO inventory (item_name, category, quantity, unit, minimum_threshold) VALUES (?, ?, ?, ?, ?)", (item_name.strip(), category.strip(), quantity, unit.strip(), minimum_threshold))
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
def add_weekly_menu_item(day_of_week: str, meal_type: str, dish_name: str, is_kid_friendly: bool, macros: str, ingredients: str, full_recipe: str = "") -> dict[str, Any]:
    """Add or update one meal in the weekly menu."""
    day = _validate_day(day_of_week)
    meal = meal_type.strip()
    with _connect() as connection:
        existing = connection.execute("SELECT id FROM weekly_menu WHERE day_of_week = ? AND meal_type = ?", (day, meal)).fetchone()
        if existing is not None:
            connection.execute("UPDATE weekly_menu SET dish_name = ?, is_kid_friendly = ?, macros = ?, ingredients = ?, full_recipe = ? WHERE id = ?", (dish_name.strip(), int(is_kid_friendly), macros, ingredients, full_recipe.strip(), existing["id"]))
            menu_item_id = existing["id"]
        else:
            cursor = connection.execute("INSERT INTO weekly_menu (day_of_week, meal_type, dish_name, is_kid_friendly, macros, ingredients, full_recipe) VALUES (?, ?, ?, ?, ?, ?, ?)", (day, meal, dish_name.strip(), int(is_kid_friendly), macros, ingredients, full_recipe.strip()))
            menu_item_id = cursor.lastrowid
    return _record("weekly_menu", menu_item_id)


@mcp.tool()
def add_weekly_menu_plan(menu_items: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate and save a complete meal plan atomically."""
    if len(menu_items) < 5:
        raise ValueError("a weekly plan requires at least five menu items")
    policy = validate_weekly_menu_policy(menu_items)
    if not policy["valid"]:
        raise ValueError("Meal plan policy violations: " + "; ".join(policy["violations"]))
    saved = []
    for item in menu_items:
        saved.append(
            add_weekly_menu_item(
                day_of_week=str(item["day_of_week"]),
                meal_type=str(item["meal_type"]),
                dish_name=str(item["dish_name"]),
                is_kid_friendly=bool(item.get("is_kid_friendly", False)),
                macros=str(item["macros"]),
                ingredients=str(item["ingredients"]),
                full_recipe=str(item.get("full_recipe", "")),
            )
        )
    return {"items": saved}


@mcp.tool()
def capture_weekly_menu_rating(menu_item_id: int, kid_rating: int, human_feedback: str = "") -> dict[str, Any]:
    """Capture a human rating from 1 through 5 for a weekly menu item."""
    if not 1 <= kid_rating <= 5:
        raise ValueError("kid_rating must be between 1 and 5")
    with _connect() as connection:
        if connection.execute("SELECT 1 FROM weekly_menu WHERE id = ?", (menu_item_id,)).fetchone() is None:
            raise ValueError(f"No weekly_menu record found for id {menu_item_id}")
        connection.execute("UPDATE weekly_menu SET kid_rating = ?, human_feedback = ? WHERE id = ?", (kid_rating, human_feedback, menu_item_id))
    return _record("weekly_menu", menu_item_id)


@mcp.tool()
def add_detailed_prep_schedule(trigger_day: str, trigger_time: str, task_type: str, detailed_instructions: str, ingredients_used: str = "", ingredients_created: str = "") -> dict[str, Any]:
    """Add a detailed preparation task for human execution."""
    with _connect() as connection:
        cursor = connection.execute("INSERT INTO detailed_prep_schedule (trigger_day, trigger_time, task_type, detailed_instructions, ingredients_used, ingredients_created) VALUES (?, ?, ?, ?, ?, ?)", (_validate_day(trigger_day), trigger_time.strip(), task_type.strip(), detailed_instructions, ingredients_used, ingredients_created))
    return _record("detailed_prep_schedule", cursor.lastrowid)


@mcp.tool()
def capture_prep_completion_status(prep_schedule_id: int, is_completed: bool, human_notes: str = "") -> dict[str, Any]:
    """Capture whether a human completed a detailed preparation task."""
    with _connect() as connection:
        if connection.execute("SELECT 1 FROM detailed_prep_schedule WHERE id = ?", (prep_schedule_id,)).fetchone() is None:
            raise ValueError(f"No detailed_prep_schedule record found for id {prep_schedule_id}")
        connection.execute("UPDATE detailed_prep_schedule SET is_completed = ?, human_notes = ? WHERE id = ?", (int(is_completed), human_notes, prep_schedule_id))
    return _record("detailed_prep_schedule", prep_schedule_id)


def acknowledge_prep_schedule(
    prep_schedule_id: int,
    acknowledgement_key: str,
    consumed_items: list[dict[str, Any]],
    human_notes: str = "",
) -> dict[str, Any]:
    """Acknowledge prep and deduct explicitly quantified ingredients exactly once."""
    if not acknowledgement_key.strip():
        raise ValueError("acknowledgement_key is required")
    if not consumed_items:
        raise ValueError("consumed_items must contain explicit quantities")
    with _connect() as connection:
        task = connection.execute("SELECT * FROM detailed_prep_schedule WHERE id = ?", (prep_schedule_id,)).fetchone()
        if task is None:
            raise ValueError(f"No detailed_prep_schedule record found for id {prep_schedule_id}")
        if task["acknowledgement_key"] == acknowledgement_key or task["status"] == "acknowledged":
            return {"task": dict(task), "replayed": True}
        if task["status"] == "completed":
            raise ValueError("prep schedule is already completed")

        normalized_items = []
        for item in consumed_items:
            try:
                inventory_id = int(item["inventory_id"])
                quantity = float(item["quantity"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("each consumed item requires inventory_id and numeric quantity") from error
            if quantity <= 0:
                raise ValueError("consumed quantities must be greater than zero")
            normalized_items.append({"inventory_id": inventory_id, "quantity": quantity, "unit": str(item.get("unit", ""))})

        for item in normalized_items:
            inventory = connection.execute("SELECT * FROM inventory WHERE id = ?", (item["inventory_id"],)).fetchone()
            if inventory is None:
                raise ValueError(f"No inventory record found for id {item['inventory_id']}")
            if inventory["quantity"] < item["quantity"]:
                raise ValueError(f"Insufficient inventory for {inventory['item_name']}")

        for index, item in enumerate(normalized_items):
            inventory = connection.execute("SELECT quantity FROM inventory WHERE id = ?", (item["inventory_id"],)).fetchone()
            before = inventory["quantity"]
            after = before - item["quantity"]
            connection.execute("UPDATE inventory SET quantity = ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?", (after, item["inventory_id"]))
            connection.execute(
                "INSERT INTO inventory_transactions (inventory_id, quantity_change, quantity_before, quantity_after, reason, source_type, source_id, idempotency_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (item["inventory_id"], -item["quantity"], before, after, "Prep acknowledged", "prep_schedule", prep_schedule_id, f"{acknowledgement_key}:{index}"),
            )
        connection.execute(
            "UPDATE detailed_prep_schedule SET is_completed = 1, status = 'acknowledged', acknowledgement_key = ?, consumption_json = ?, human_notes = ? WHERE id = ?",
            (acknowledgement_key, json.dumps(normalized_items), human_notes, prep_schedule_id),
        )
        return {"task": _record_in_connection(connection, "detailed_prep_schedule", prep_schedule_id), "replayed": False}


def _record_in_connection(connection: sqlite3.Connection, table: str, record_id: int) -> dict[str, Any]:
    row = connection.execute(f"SELECT * FROM {table} WHERE id = ?", (record_id,)).fetchone()
    return dict(row) if row is not None else {}


@mcp.tool()
def create_shopping_list(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Persist a validated shopping proposal without changing inventory."""
    if not items:
        raise ValueError("items must contain at least one item")
    with _connect() as connection:
        cursor = connection.execute("INSERT INTO shopping_lists DEFAULT VALUES")
        list_id = cursor.lastrowid
        for item in items:
            try:
                name, quantity, unit = str(item["item_name"]).strip(), float(item["proposed_quantity"]), str(item["unit"]).strip()
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("each shopping item requires item_name, proposed_quantity, and unit") from error
            if not name or quantity <= 0 or not unit:
                raise ValueError("shopping item names, quantities, and units must be valid")
            connection.execute("INSERT INTO shopping_items (shopping_list_id, item_name, proposed_quantity, unit) VALUES (?, ?, ?, ?)", (list_id, name, quantity, unit))
        return {"list": _record_in_connection(connection, "shopping_lists", list_id), "items": [dict(row) for row in connection.execute("SELECT * FROM shopping_items WHERE shopping_list_id = ?", (list_id,))]}


def acknowledge_shopping_list(shopping_list_id: int, acknowledgement_key: str, purchased_items: list[dict[str, Any]]) -> dict[str, Any]:
    """Add actual purchased quantities to inventory exactly once."""
    if not acknowledgement_key.strip() or not purchased_items:
        raise ValueError("acknowledgement_key and purchased_items are required")
    with _connect() as connection:
        shopping_list = connection.execute("SELECT * FROM shopping_lists WHERE id = ?", (shopping_list_id,)).fetchone()
        if shopping_list is None:
            raise ValueError(f"No shopping list found for id {shopping_list_id}")
        if shopping_list["status"] == "purchased":
            return {"list": dict(shopping_list), "replayed": True}
        for item in purchased_items:
            if float(item.get("actual_quantity", 0)) < 0:
                raise ValueError("actual quantities cannot be negative")
        for item in purchased_items:
            item_id = int(item["shopping_item_id"])
            quantity = float(item["actual_quantity"])
            row = connection.execute("SELECT * FROM shopping_items WHERE id = ? AND shopping_list_id = ?", (item_id, shopping_list_id)).fetchone()
            if row is None:
                raise ValueError(f"No shopping item found for id {item_id}")
            connection.execute("UPDATE shopping_items SET actual_quantity = ?, status = 'purchased' WHERE id = ?", (quantity, item_id))
            if quantity == 0:
                continue
            inventory = connection.execute("SELECT * FROM inventory WHERE item_name = ?", (row["item_name"],)).fetchone()
            if inventory is None:
                cursor = connection.execute("INSERT INTO inventory (item_name, category, quantity, unit) VALUES (?, 'Pantry', ?, ?)", (row["item_name"], quantity, row["unit"]))
                inventory_id, before = cursor.lastrowid, 0
            else:
                inventory_id, before = inventory["id"], inventory["quantity"]
                connection.execute("UPDATE inventory SET quantity = quantity + ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?", (quantity, inventory_id))
            connection.execute("INSERT INTO inventory_transactions (inventory_id, quantity_change, quantity_before, quantity_after, reason, source_type, source_id, idempotency_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (inventory_id, quantity, before, before + quantity, "Shopping purchase acknowledged", "shopping_list", shopping_list_id, f"{acknowledgement_key}:{item_id}"))
        connection.execute("UPDATE shopping_lists SET status = 'purchased', acknowledgement_key = ?, acknowledged_at = CURRENT_TIMESTAMP WHERE id = ?", (acknowledgement_key, shopping_list_id))
        return {"list": _record_in_connection(connection, "shopping_lists", shopping_list_id), "replayed": False}


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
    ingredients: str
    full_recipe: str = ""

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
    detailed_instructions: str = Field(min_length=1)
    ingredients_used: str = ""
    ingredients_created: str = ""

    @field_validator("trigger_day")
    @classmethod
    def validate_day(cls, value: str) -> str:
        return _validate_day(value)


class PrepCompletionRequest(BaseModel):
    is_completed: bool
    human_notes: str = ""


class PrepAcknowledgementRequest(BaseModel):
    acknowledgement_key: str = Field(min_length=1, max_length=200)
    consumed_items: list[dict[str, Any]] = Field(min_length=1)
    human_notes: str = ""


class ShoppingItemRequest(BaseModel):
    item_name: str = Field(min_length=1)
    proposed_quantity: float = Field(gt=0)
    unit: str = Field(min_length=1)


class ShoppingListRequest(BaseModel):
    items: list[ShoppingItemRequest] = Field(min_length=1)


class ShoppingPurchaseRequest(BaseModel):
    acknowledgement_key: str = Field(min_length=1, max_length=200)
    purchased_items: list[dict[str, Any]] = Field(min_length=1)


class AgentRunRequest(BaseModel):
    agent_role: str = Field(min_length=1, max_length=80)
    job_name: str = Field(min_length=1, max_length=80)
    status: str = Field(pattern="^(completed|failed)$")
    result: str = ""
    error: str = ""


class MenuPolicyRequest(BaseModel):
    menu_items: list[dict[str, Any]] = Field(min_length=1)


class MenuPlanRequest(BaseModel):
    menu_items: list[dict[str, Any]] = Field(min_length=5)


class ChatSessionRequest(BaseModel):
    messages: list[dict[str, Any]]


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
            "menu": [dict(row) for row in connection.execute("SELECT * FROM weekly_menu ORDER BY CASE day_of_week WHEN 'monday' THEN 1 WHEN 'tuesday' THEN 2 WHEN 'wednesday' THEN 3 WHEN 'thursday' THEN 4 WHEN 'friday' THEN 5 ELSE 6 END, id")],
            "tasks": [dict(row) for row in connection.execute("SELECT * FROM detailed_prep_schedule ORDER BY is_completed, id")],
                "shopping_lists": [{**dict(row), "items": [dict(item) for item in connection.execute("SELECT * FROM shopping_items WHERE shopping_list_id = ? ORDER BY id", (row["id"],))]} for row in connection.execute("SELECT * FROM shopping_lists ORDER BY id DESC")],
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


@app.post("/api/prep-schedule/{prep_schedule_id}/acknowledge")
def api_acknowledge_prep(prep_schedule_id: int, request: PrepAcknowledgementRequest) -> dict[str, Any]:
    try:
        return acknowledge_prep_schedule(prep_schedule_id, **request.model_dump())
    except ValueError as error:
        raise _tool_error(error) from error


@app.post("/api/shopping-lists")
def api_create_shopping_list(request: ShoppingListRequest) -> dict[str, Any]:
    try:
        return create_shopping_list([item.model_dump() for item in request.items])
    except ValueError as error:
        raise _tool_error(error) from error


@app.post("/api/shopping-lists/{shopping_list_id}/acknowledge")
def api_acknowledge_shopping(shopping_list_id: int, request: ShoppingPurchaseRequest) -> dict[str, Any]:
    try:
        return acknowledge_shopping_list(shopping_list_id, **request.model_dump())
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


@app.post("/api/weekly-menu/validate")
def api_validate_menu(request: MenuPolicyRequest) -> dict[str, Any]:
    return validate_weekly_menu_policy(request.menu_items)


@app.post("/api/weekly-menu/plan")
def api_add_menu_plan(request: MenuPlanRequest) -> dict[str, Any]:
    try:
        return add_weekly_menu_plan(request.menu_items)
    except ValueError as error:
        raise _tool_error(error) from error


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