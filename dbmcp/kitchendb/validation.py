"""Pure input validation and normalization - no database access.

These helpers are shared by the data operations (kitchendb/tools/) and by the Pydantic
request models (kitchendb/models.py).
"""

from __future__ import annotations

import re
from typing import Any

from constants import DAY_SET, MEAL_TYPE_SET

from .units import canonicalize_inventory_unit

# weekly_menu.ingredients / .full_recipe and detailed_prep_schedule.detailed_instructions
# are all JSON string arrays of short plain-text lines. Cap the count so a runaway model
# can't bloat a row.
MENU_LINES_LIMIT = 40

# Ingredients/terms that must never appear in a weekday lunch (school policy).
RESTRICTED_LUNCH_TERMS = ("egg", "chicken", "beef", "pork", "fish", "meat", "turkey", "seafood")


def validate_day(day_of_week: str) -> str:
    normalized = day_of_week.strip().lower()
    if normalized not in DAY_SET:
        raise ValueError("day_of_week must be a full weekday name")
    return normalized


def validate_meal_type(meal_type: str) -> str:
    normalized = meal_type.strip().lower()
    if normalized not in MEAL_TYPE_SET:
        raise ValueError(f"meal_type must be one of {sorted(MEAL_TYPE_SET)}")
    return normalized


def clean_line_list(value: Any, *, field: str, required: bool) -> list[str]:
    """Normalize a JSON string-array field into a clean list of non-empty lines.

    Accepts a list; trims blanks; caps the count at MENU_LINES_LIMIT.
    """
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list of strings")
    lines = [str(item).strip() for item in value if str(item).strip()]
    if required and not lines:
        raise ValueError(f"{field} must contain at least one non-empty string")
    if len(lines) > MENU_LINES_LIMIT:
        raise ValueError(f"{field} cannot have more than {MENU_LINES_LIMIT} items")
    return lines


def normalize_ingredients_used(ingredients_used: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Validate raw {item_name, quantity, unit} entries into a clean deduction list.

    Keyed by item_name (case-insensitive), matching inventory's own key - never by
    inventory_id, which the caller has no reliable way to know ahead of time.
    """
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


def menu_policy_violations(menu_items: list[dict[str, Any]]) -> list[str]:
    """Check school-lunch restrictions and weekday lunch variety across a menu."""
    violations: list[str] = []
    lunch_dishes: list[str] = []
    for item in menu_items:
        meal_type = str(item.get("meal_type", "")).strip().lower()
        dish_name = str(item.get("dish_name", "")).strip()
        ingredients = str(item.get("ingredients", "")).lower()
        if meal_type == "lunch":
            lunch_dishes.append(dish_name.lower())
            restricted = [
                term
                for term in RESTRICTED_LUNCH_TERMS
                if re.search(rf"\b{re.escape(term)}\b", f"{dish_name.lower()} {ingredients}")
            ]
            if restricted:
                violations.append(f"{dish_name} contains restricted lunch ingredient: {restricted[0]}")
    if len(lunch_dishes) >= 5 and len(set(lunch_dishes)) < 5:
        violations.append("Weekday lunches must contain five distinct preparations")
    return violations
