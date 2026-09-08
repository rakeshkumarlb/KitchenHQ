"""Household-profile data operations.

get_user_profile / update_user_profile are REST-only (no decorator);
get_household_preferences is the MCP tool agents call before planning a week.
"""

from __future__ import annotations

import json
from typing import Any

from .registry import tool
from ..db import connect


def get_user_profile() -> dict[str, Any]:
    """Read the single household profile row (name, contact email, preferences)."""
    with connect() as connection:
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
    with connect() as connection:
        connection.execute("INSERT OR IGNORE INTO user_profile (id) VALUES (1)")
        connection.execute(
            f"UPDATE user_profile SET {', '.join(assignments)}, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
            values,
        )
    return get_user_profile()


@tool
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
