"""Pure input validation and normalization - no database access.

These helpers are shared by the data operations (kitchendb/tools/) and by the Pydantic
request models (kitchendb/models.py).
"""

from __future__ import annotations

from typing import Any

from constants import DAY_SET, MEAL_TYPE_SET

from .units import canonicalize_inventory_unit

# weekly_menu.ingredients / .full_recipe and detailed_prep_schedule.detailed_instructions
# are all JSON string arrays of short plain-text lines. Cap the count so a runaway model
# can't bloat a row.
MENU_LINES_LIMIT = 40

# recipes.recipe.description and weekly_menu.description are a sentence or two, not a
# full recap - cap the length so a runaway model can't turn it into a second instructions
# field.
DESCRIPTION_MAX_LENGTH = 300


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


def clean_short_text(value: Any, *, field: str, required: bool) -> str:
    """Normalize a short free-text field (e.g. a recipe/dish description).

    Trims whitespace and caps length at DESCRIPTION_MAX_LENGTH; required=True rejects
    an empty result.
    """
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{field} must not be empty")
    if len(text) > DESCRIPTION_MAX_LENGTH:
        raise ValueError(f"{field} cannot be longer than {DESCRIPTION_MAX_LENGTH} characters")
    return text


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
