"""MCP server exposing KitchenHQ's SQLite database to agents."""

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

DATABASE_PATH = Path(os.environ.get("KITCHEN_DB_PATH", Path(__file__).with_name("kitchen.db")))
TABLES = {"inventory", "wastage_log", "weekly_menu", "prep_schedule", "task_acknowledgement", "meal_feedback"}
mcp = FastMCP("KitchenHQ Database")


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _rows(table: str, where: str = "", parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    if table not in TABLES:
        raise ValueError(f"Unknown table: {table}")
    with _connect() as connection:
        cursor = connection.execute(f"SELECT * FROM {table}{where} ORDER BY id DESC", parameters)
        return [dict(row) for row in cursor.fetchall()]


def _insert(table: str, values: dict[str, Any]) -> dict[str, Any]:
    if table not in TABLES or not values:
        raise ValueError("Invalid table or empty record")
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    with _connect() as connection:
        cursor = connection.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(values.values()))
        return dict(connection.execute(f"SELECT * FROM {table} WHERE id = ?", (cursor.lastrowid,)).fetchone())


@mcp.tool()
def list_tables() -> list[str]:
    """Return the database tables available to KitchenHQ agents."""
    return sorted(TABLES)


@mcp.tool()
def query_table(table: str, limit: int = 50) -> list[dict[str, Any]]:
    """Read recent records from a KitchenHQ table."""
    if not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200")
    return _rows(table)[:limit]


@mcp.tool()
def search_inventory(item_name: str = "", below_threshold_only: bool = False) -> list[dict[str, Any]]:
    """Find ingredients, optionally returning only items at or below their reorder threshold."""
    where = " WHERE quantity <= minimum_threshold" if below_threshold_only else ""
    parameters: tuple[Any, ...] = ()
    if item_name:
        where += " AND item_name LIKE ?" if where else " WHERE item_name LIKE ?"
        parameters = (f"%{item_name}%",)
    return _rows("inventory", where, parameters)


@mcp.tool()
def upsert_inventory(item_name: str, quantity: float, unit: str, category: str = "Pantry", minimum_threshold: float = 0) -> dict[str, Any]:
    """Create or update an ingredient's current stock."""
    if quantity < 0 or minimum_threshold < 0:
        raise ValueError("quantity and minimum_threshold cannot be negative")
    with _connect() as connection:
        existing = connection.execute("SELECT id FROM inventory WHERE lower(item_name) = lower(?)", (item_name,)).fetchone()
        if existing:
            connection.execute("UPDATE inventory SET quantity = ?, unit = ?, category = ?, minimum_threshold = ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?", (quantity, unit, category, minimum_threshold, existing["id"]))
            return dict(connection.execute("SELECT * FROM inventory WHERE id = ?", (existing["id"],)).fetchone())
    return _insert("inventory", {"item_name": item_name, "category": category, "quantity": quantity, "unit": unit, "minimum_threshold": minimum_threshold})


@mcp.tool()
def log_wastage(item_name: str, quantity_wasted: float) -> dict[str, Any]:
    """Record discarded ingredients for future grocery planning."""
    if quantity_wasted <= 0:
        raise ValueError("quantity_wasted must be greater than zero")
    return _insert("wastage_log", {"item_name": item_name, "quantity_wasted": quantity_wasted})


@mcp.tool()
def save_menu_item(day_of_week: str, meal_type: str, dish_name: str, is_kid_friendly: bool, macros: str, ingredients: str) -> dict[str, Any]:
    """Save one planned meal to the weekly menu."""
    return _insert("weekly_menu", {"day_of_week": day_of_week, "meal_type": meal_type, "dish_name": dish_name, "is_kid_friendly": int(is_kid_friendly), "macros": macros, "ingredients": ingredients})


@mcp.tool()
def save_prep_task(trigger_day: str, trigger_time: str, task_type: str, instructions: str) -> dict[str, Any]:
    """Save an actionable preparation task to the recurring prep schedule."""
    return _insert("prep_schedule", {"trigger_day": trigger_day, "trigger_time": trigger_time, "task_type": task_type, "instructions": instructions})


@mcp.tool()
def record_feedback(date_served: str, dish_name: str, kid_rating: int, human_feedback: str = "") -> dict[str, Any]:
    """Record meal feedback; kid ratings must be from 1 through 5."""
    if not 1 <= kid_rating <= 5:
        raise ValueError("kid_rating must be between 1 and 5")
    return _insert("meal_feedback", {"date_served": date_served, "dish_name": dish_name, "kid_rating": kid_rating, "human_feedback": human_feedback})


@mcp.tool()
def acknowledge_task(task_date: str, task_type: str, task_description: str, is_completed: bool, human_notes: str = "") -> dict[str, Any]:
    """Record whether a preparation task was completed or skipped."""
    return _insert("task_acknowledgement", {"task_date": task_date, "task_type": task_type, "task_description": task_description, "is_completed": int(is_completed), "human_notes": human_notes})


@mcp.resource("kitchen://schema")
def schema_resource() -> str:
    """Return the KitchenHQ schema and table descriptions."""
    return Path(__file__).with_name("db_design.md").read_text(encoding="utf-8")


@mcp.resource("kitchen://table/{table}")
def table_resource(table: str) -> str:
    """Return current records from one known KitchenHQ table as JSON."""
    return json.dumps(_rows(table), indent=2, default=str)


@mcp.prompt()
def inventory_agent(task: str = "Review stock and identify ingredients to replenish") -> str:
    """Prompt an agent to use the inventory tools before making claims."""
    return f"You are the KitchenHQ Inventory Agent. {task}\nRead kitchen://schema first, then use search_inventory and query_table before responding. Use upsert_inventory and log_wastage for changes."


@mcp.prompt()
def chef_agent(task: str = "Create a macro-balanced Monday-Friday menu") -> str:
    """Prompt an agent to plan meals from current stock and feedback."""
    return f"You are the KitchenHQ Executive Chef. {task}\nRead kitchen://schema, then query inventory, meal_feedback, and task_acknowledgement. Save each approved meal with save_menu_item and report saved IDs."


@mcp.prompt()
def sous_chef_agent(task: str = "Create today's preparation plan") -> str:
    """Prompt an agent to create and acknowledge preparation work."""
    return f"You are the KitchenHQ Sous-Chef. {task}\nQuery weekly_menu before planning, save actionable work with save_prep_task, and use acknowledge_task when a human reports completion."


if __name__ == "__main__":
    mcp.run()