"""Household-profile data operations.

get_user_profile / update_user_profile are REST-only (no decorator);
get_household_preferences is the MCP tool agents call before planning a week.
Household-member CRUD (add/update/delete/list_household_members) is REST-only too -
these are edited by a human on the Profile page, not written by an agent.
"""

from __future__ import annotations

import json
from typing import Any

from .registry import tool
from ..db import connect, fetch_record
from ..validation import validate_day, validate_meal_type

_VALID_RESTRICTION_SCOPES = {"per_meal", "week"}


def get_user_profile() -> dict[str, Any]:
    """Read the single household profile row (name, contact email, preferences)."""
    with connect() as connection:
        row = connection.execute("SELECT * FROM user_profile WHERE id = 1").fetchone()
    return dict(row) if row is not None else {}


def _validate_restrictions(value: Any) -> list[dict[str, Any]]:
    """Validate the household's configurable restriction list.

    Each entry needs a unique `id`, a human `label`, and a `scope` of "per_meal" (judged
    per weekly_menu row by menu_audit) or "week" (judged once per week across the whole
    saved menu by weekly_plan_audit). `value` is an optional rule-specific parameter
    (e.g. a minimum distinct-preparations count) and is preserved as given.
    """
    if not isinstance(value, list):
        raise ValueError("restrictions must be a list")
    cleaned: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError("each restriction must be an object")
        restriction_id = str(entry.get("id", "")).strip()
        label = str(entry.get("label", "")).strip()
        if not restriction_id or not label:
            raise ValueError("each restriction requires a non-empty id and label")
        if restriction_id in seen_ids:
            raise ValueError(f"duplicate restriction id: {restriction_id}")
        seen_ids.add(restriction_id)
        scope = str(entry.get("scope", "")).strip().lower()
        if scope not in _VALID_RESTRICTION_SCOPES:
            raise ValueError(f"restriction '{restriction_id}' scope must be one of {sorted(_VALID_RESTRICTION_SCOPES)}")
        cleaned_entry: dict[str, Any] = {
            "id": restriction_id,
            "label": label,
            "category": str(entry.get("category", "")).strip(),
            "enabled": bool(entry.get("enabled", True)),
            "scope": scope,
        }
        if entry.get("value") is not None:
            cleaned_entry["value"] = entry["value"]
        cleaned.append(cleaned_entry)
    return cleaned


def _validate_skip_meals(value: Any) -> dict[str, list[str]]:
    """Validate {day_of_week: [meal_type, ...]} - slots the household wants left unplanned."""
    if not isinstance(value, dict):
        raise ValueError("skip_meals must be an object of {day_of_week: [meal_type, ...]}")
    cleaned: dict[str, list[str]] = {}
    for day, meals in value.items():
        day_key = validate_day(day)
        if not isinstance(meals, list):
            raise ValueError(f"skip_meals['{day}'] must be a list of meal types")
        meal_list = sorted({validate_meal_type(meal) for meal in meals})
        if meal_list:
            cleaned[day_key] = meal_list
    return cleaned


def _validate_tag_list(value: Any, *, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list of strings")
    return [str(tag).strip() for tag in value if str(tag).strip()]


def update_user_profile(
    name: str | None = None,
    email: str | None = None,
    cc_emails: str | None = None,
    notes: str | None = None,
    notify_on_task_creation: bool | None = None,
    restrictions: list[dict[str, Any]] | None = None,
    allow_recipe_invention: bool | None = None,
    allow_unapproved_recipes: bool | None = None,
    skip_meals: dict[str, list[str]] | None = None,
    preferred_tags: list[str] | None = None,
    excluded_tags: list[str] | None = None,
) -> dict[str, Any]:
    """Patch the household profile. Only the fields passed (non-None) are changed.

    `cc_emails` is a free-form string of extra addresses (comma/semicolon/newline
    separated) copied on task-alert emails. `favorite_recipes` is not patchable here.
    `restrictions`/`skip_meals`/`preferred_tags`/`excluded_tags` are stored as JSON - see
    _validate_restrictions/_validate_skip_meals for their shapes.
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
    if allow_recipe_invention is not None:
        assignments.append("allow_recipe_invention = ?")
        values.append(int(bool(allow_recipe_invention)))
    if allow_unapproved_recipes is not None:
        assignments.append("allow_unapproved_recipes = ?")
        values.append(int(bool(allow_unapproved_recipes)))
    if restrictions is not None:
        assignments.append("restrictions = ?")
        values.append(json.dumps(_validate_restrictions(restrictions)))
    if skip_meals is not None:
        assignments.append("skip_meals = ?")
        values.append(json.dumps(_validate_skip_meals(skip_meals)))
    if preferred_tags is not None:
        assignments.append("preferred_tags = ?")
        values.append(json.dumps(_validate_tag_list(preferred_tags, field="preferred_tags")))
    if excluded_tags is not None:
        assignments.append("excluded_tags = ?")
        values.append(json.dumps(_validate_tag_list(excluded_tags, field="excluded_tags")))
    if not assignments:
        return get_user_profile()
    with connect() as connection:
        connection.execute("INSERT OR IGNORE INTO user_profile (id) VALUES (1)")
        connection.execute(
            f"UPDATE user_profile SET {', '.join(assignments)}, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
            values,
        )
    return get_user_profile()


def _parse_json_list(raw: Any) -> list[str]:
    try:
        value = json.loads(raw or "[]")
        return value if isinstance(value, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def list_household_members() -> list[dict[str, Any]]:
    """Read every household member, each with their dietary preferences and health conditions."""
    with connect() as connection:
        rows = [dict(row) for row in connection.execute("SELECT * FROM household_members ORDER BY id")]
    for row in rows:
        row["dietary_preferences"] = _parse_json_list(row.get("dietary_preferences"))
        row["health_conditions"] = _parse_json_list(row.get("health_conditions"))
    return rows


def add_household_member(
    name: str, dietary_preferences: list[str] | None = None, health_conditions: list[str] | None = None
) -> dict[str, Any]:
    """Add one household member with their dietary preferences and health conditions."""
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("name must not be empty")
    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO household_members (name, dietary_preferences, health_conditions) VALUES (?, ?, ?)",
            (clean_name, json.dumps([p.strip() for p in dietary_preferences or [] if p.strip()]),
             json.dumps([c.strip() for c in health_conditions or [] if c.strip()])),
        )
    member = fetch_record("household_members", cursor.lastrowid)
    member["dietary_preferences"] = _parse_json_list(member.get("dietary_preferences"))
    member["health_conditions"] = _parse_json_list(member.get("health_conditions"))
    return member


def update_household_member(
    member_id: int,
    name: str | None = None,
    dietary_preferences: list[str] | None = None,
    health_conditions: list[str] | None = None,
) -> dict[str, Any]:
    """Patch one household member. Only the fields passed (non-None) are changed."""
    assignments: list[str] = []
    values: list[Any] = []
    if name is not None:
        if not name.strip():
            raise ValueError("name must not be empty")
        assignments.append("name = ?")
        values.append(name.strip())
    if dietary_preferences is not None:
        assignments.append("dietary_preferences = ?")
        values.append(json.dumps([p.strip() for p in dietary_preferences if p.strip()]))
    if health_conditions is not None:
        assignments.append("health_conditions = ?")
        values.append(json.dumps([c.strip() for c in health_conditions if c.strip()]))
    if assignments:
        values.append(member_id)
        with connect() as connection:
            cursor = connection.execute(
                f"UPDATE household_members SET {', '.join(assignments)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                values,
            )
            if cursor.rowcount == 0:
                raise ValueError(f"No household_members record found for id {member_id}")
    member = fetch_record("household_members", member_id)
    member["dietary_preferences"] = _parse_json_list(member.get("dietary_preferences"))
    member["health_conditions"] = _parse_json_list(member.get("health_conditions"))
    return member


def delete_household_member(member_id: int) -> dict[str, Any]:
    """Remove one household member."""
    with connect() as connection:
        cursor = connection.execute("DELETE FROM household_members WHERE id = ?", (member_id,))
    if cursor.rowcount == 0:
        raise ValueError(f"No household_members record found for id {member_id}")
    return {"deleted": True, "id": member_id}


def _parse_json_object(raw: Any) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


@tool
def get_household_preferences() -> dict[str, Any]:
    """Shared planning/evaluation context set by the household on the profile screen.

    Returns the chef's free-text note, the household's most recently top-rated dishes
    (up to 10, newest first, each with its star rating and when it was rated), the list
    of household members with their individual dietary preferences and health
    conditions, the household's configured `restrictions` (each with a `scope` of
    "per_meal" or "week" - judge per_meal ones against each weekly_menu row, week ones
    against the whole saved week), `allow_recipe_invention`/`allow_unapproved_recipes`,
    `skip_meals` (day/meal slots to leave unplanned this week), and `preferred_tags`/
    `excluded_tags`. This is the single source of household rules/preferences consulted
    by every role - Executive Chef and Sous Chef before deciding what to cook, and Food
    Inspector when auditing what they decided - so it must never be duplicated
    elsewhere; always call this tool rather than assuming preferences or rules from
    memory. There is no separate deterministic policy check - restrictions here are the
    only source of truth for what's allowed.
    """
    profile = get_user_profile()
    favorites = _parse_json_list(profile.get("favorite_recipes"))
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
    members = list_household_members()
    if favorite_recipes or chef_note.strip() or members:
        guidance = "Weight these favourites, the note, and each member's preferences/conditions when planning or auditing, within the dietary rules."
    else:
        guidance = (
            "No saved favourites, chef note, or household members yet - this is optional context, not a "
            "blocker. Plan or audit from current inventory, the dietary and macro rules, and everyday variety."
        )
    return {
        "chef_note": chef_note,
        "favorite_recipes": favorite_recipes,
        "household_members": members,
        "restrictions": _parse_json_list(profile.get("restrictions")),
        "allow_recipe_invention": bool(profile.get("allow_recipe_invention", 1)),
        "allow_unapproved_recipes": bool(profile.get("allow_unapproved_recipes", 1)),
        "skip_meals": _parse_json_object(profile.get("skip_meals")),
        "preferred_tags": _parse_json_list(profile.get("preferred_tags")),
        "excluded_tags": _parse_json_list(profile.get("excluded_tags")),
        "has_preferences": bool(favorite_recipes or chef_note.strip() or members),
        "guidance": guidance,
    }
