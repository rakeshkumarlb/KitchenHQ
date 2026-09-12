"""Weekly-menu data operations."""

from __future__ import annotations

import json
from typing import Any

from .registry import tool
from ..db import connect
from ..validation import (
    clean_line_list,
    menu_policy_violations,
    validate_day,
    validate_meal_type,
)


@tool
def get_weekly_menu() -> list[dict[str, Any]]:
    """Read the saved weekly menu."""
    with connect() as connection:
        return [dict(row) for row in connection.execute("SELECT * FROM weekly_menu ORDER BY id")]


@tool
def validate_weekly_menu_policy(menu_items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Validate macros, school lunch restrictions, and weekday lunch variety."""
    if menu_items is None:
        with connect() as connection:
            menu_items = [dict(row) for row in connection.execute("SELECT * FROM weekly_menu ORDER BY id")]
    violations = menu_policy_violations(menu_items)
    return {"valid": not violations, "violations": violations}


@tool
def add_weekly_menu_item(
    day_of_week: str,
    meal_type: str,
    dish_name: str,
    is_kid_friendly: bool,
    macros: str,
    ingredients: list[str],
    full_recipe: list[str] | None = None,
) -> dict[str, Any]:
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
    day = validate_day(day_of_week)
    meal = validate_meal_type(meal_type)
    ingredient_lines = clean_line_list(ingredients, field="ingredients", required=True)
    recipe_lines = clean_line_list(full_recipe or [], field="full_recipe", required=False)
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO weekly_menu (day_of_week, meal_type, dish_name, is_kid_friendly, macros, ingredients, full_recipe, score, audit_feedback, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(day_of_week, meal_type) DO UPDATE SET
                dish_name = excluded.dish_name,
                is_kid_friendly = excluded.is_kid_friendly,
                macros = excluded.macros,
                ingredients = excluded.ingredients,
                full_recipe = excluded.full_recipe,
                score = NULL,
                audit_feedback = NULL,
                updated_at = CURRENT_TIMESTAMP
            """,
            (day, meal, dish_name.strip(), int(is_kid_friendly), macros, json.dumps(ingredient_lines), json.dumps(recipe_lines), None, None),
        )
        row = connection.execute(
            "SELECT * FROM weekly_menu WHERE day_of_week = ? AND meal_type = ?", (day, meal)
        ).fetchone()
    return dict(row)
