"""Weekly-menu data operations, including rating capture and favourite-recipe sync."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .registry import tool
from ..db import connect, fetch_record
from ..validation import (
    FAVORITE_RECIPES_LIMIT,
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
        row = connection.execute(
            "SELECT * FROM weekly_menu WHERE day_of_week = ? AND meal_type = ?", (day, meal)
        ).fetchone()
    return dict(row)


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


@tool
def capture_weekly_menu_rating(menu_item_id: int, kid_rating: int, human_feedback: str = "") -> dict[str, Any]:
    """Capture a human rating from 1 through 5 for a weekly menu item.

    A rating of 4 or 5 also records the dish in the household's top-10 favourite
    recipes (newest first); a lower rating removes it if it was there.
    """
    if not 1 <= kid_rating <= 5:
        raise ValueError("kid_rating must be between 1 and 5")
    with connect() as connection:
        menu_row = connection.execute("SELECT dish_name FROM weekly_menu WHERE id = ?", (menu_item_id,)).fetchone()
        if menu_row is None:
            raise ValueError(f"No weekly_menu record found for id {menu_item_id}")
        connection.execute(
            "UPDATE weekly_menu SET kid_rating = ?, human_feedback = ? WHERE id = ?",
            (kid_rating, human_feedback, menu_item_id),
        )
        _sync_favorite_recipes(connection, menu_row["dish_name"], kid_rating)
    return fetch_record("weekly_menu", menu_item_id)
