"""Weekly-menu data operations.

`mark_weekly_menu_skipped` is REST-only, mirroring `weekly_plan.py::upsert_weekly_plan` -
see its docstring for why a skipped slot needs an explicit placeholder rather than being
left untouched.
"""

from __future__ import annotations

import json
from typing import Any

from .registry import tool
from ..db import connect, fetch_record_in
from ..validation import (
    clean_line_list,
    clean_short_text,
    validate_day,
    validate_meal_type,
)


@tool
def get_weekly_menu() -> list[dict[str, Any]]:
    """Read the saved weekly menu."""
    with connect() as connection:
        return [dict(row) for row in connection.execute("SELECT * FROM weekly_menu ORDER BY id")]


@tool
def add_weekly_menu_item(
    day_of_week: str,
    meal_type: str,
    dish_name: str,
    is_kid_friendly: bool,
    macros: str,
    ingredients: list[str],
    description: str,
    full_recipe: list[str] | None = None,
    tags: list[str] | None = None,
    source_recipe_id: int | None = None,
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
      description: a short (one or two sentence) plain-text summary of the dish - what it
        is, its character. Required, like dish_name. Shown on the Weekly Menu page's meal
        card in place of a raw ingredient/macro preview.
      full_recipe: ordered list of method-step strings, plain text (no HTML / markdown).
        Stored as a JSON array; rendered as a numbered list.
      tags: same freeform taxonomy as a recipes catalog entry's tags (diet category,
        allergen/nutrition labels, cuisine/method - see the recipe catalog standards) -
        shown in this meal's recipe modal the same way the catalog shows a recipe's tags.
      source_recipe_id: the `recipes` catalog id this dish was adapted from via
        search_recipes, if any - leave None when the dish was invented or transcribed
        fresh for this slot only. Recorded so a later "recreate instructions"/"identify
        tags" request for this slot knows which record is authoritative: the linked
        catalog recipe when this is set, this weekly_menu row directly when it's None.
    """
    day = validate_day(day_of_week)
    meal = validate_meal_type(meal_type)
    ingredient_lines = clean_line_list(ingredients, field="ingredients", required=True)
    recipe_lines = clean_line_list(full_recipe or [], field="full_recipe", required=False)
    description_text = clean_short_text(description, field="description", required=True)
    tag_lines = clean_line_list(tags or [], field="tags", required=False)
    with connect() as connection:
        if source_recipe_id is not None and not fetch_record_in(connection, "recipes", source_recipe_id):
            raise ValueError(f"No recipes record found for id {source_recipe_id}")
        connection.execute(
            """
            INSERT INTO weekly_menu (day_of_week, meal_type, dish_name, is_kid_friendly, macros, ingredients, full_recipe, description, tags, source_recipe_id, score, audit_feedback, is_skipped, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
            ON CONFLICT(day_of_week, meal_type) DO UPDATE SET
                dish_name = excluded.dish_name,
                is_kid_friendly = excluded.is_kid_friendly,
                macros = excluded.macros,
                ingredients = excluded.ingredients,
                full_recipe = excluded.full_recipe,
                description = excluded.description,
                tags = excluded.tags,
                source_recipe_id = excluded.source_recipe_id,
                score = NULL,
                audit_feedback = NULL,
                is_skipped = 0,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                day, meal, dish_name.strip(), int(is_kid_friendly), macros,
                json.dumps(ingredient_lines), json.dumps(recipe_lines), description_text,
                json.dumps(tag_lines), source_recipe_id, None, None,
            ),
        )
        row = connection.execute(
            "SELECT * FROM weekly_menu WHERE day_of_week = ? AND meal_type = ?", (day, meal)
        ).fetchone()
    return dict(row)


def mark_weekly_menu_skipped(slots: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Write a "skipped" placeholder for each (day_of_week, meal_type) slot the
    household's skip_meals config excludes this run.

    REST-only (no `@tool` decorator), like `upsert_weekly_plan` - called deterministically
    by agent-api's `run_job` right after a successful `weekly_menu` job, for exactly the
    slots that job's skip_meals snapshot excluded (the Executive Chef is told not to call
    add_weekly_menu_item for these). Without this, a slot skipped this week but planned
    with a real dish in an earlier week would keep showing that stale dish forever, since
    nothing else ever touches the row. Pre-scored (score=100, a fixed audit_feedback) so
    the placeholder never surfaces in get_unaudited_weekly_menu_items for the Food
    Inspector to judge. Saving a real dish for the slot again later via
    add_weekly_menu_item clears is_skipped back to 0 and resets score/audit_feedback to
    NULL, same as any other re-plan.
    """
    results = []
    with connect() as connection:
        for slot in slots:
            day = validate_day(slot["day_of_week"])
            meal = validate_meal_type(slot["meal_type"])
            connection.execute(
                """
                INSERT INTO weekly_menu (
                    day_of_week, meal_type, dish_name, is_kid_friendly, macros,
                    ingredients, full_recipe, description, tags, source_recipe_id,
                    score, audit_feedback, is_skipped, updated_at
                )
                VALUES (?, ?, 'Skipped', 0, '', '[]', '[]', '', '[]', NULL, 100, ?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(day_of_week, meal_type) DO UPDATE SET
                    dish_name = 'Skipped',
                    is_kid_friendly = 0,
                    macros = '',
                    ingredients = '[]',
                    full_recipe = '[]',
                    description = '',
                    tags = '[]',
                    source_recipe_id = NULL,
                    score = 100,
                    audit_feedback = excluded.audit_feedback,
                    is_skipped = 1,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (day, meal, "Skipped by household preference this week - not planned."),
            )
            row = connection.execute(
                "SELECT * FROM weekly_menu WHERE day_of_week = ? AND meal_type = ?", (day, meal)
            ).fetchone()
            results.append(dict(row))
    return results
