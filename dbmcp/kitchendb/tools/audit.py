"""Food Inspector data operations: find unaudited rows, record a score + feedback.

The Food Inspector is an LLM-as-judge role that evaluates decisions the Executive Chef
(weekly_menu, recipes) and Sous Chef (detailed_prep_schedule) already made, against the
same household rules/preferences/conditions and recipe catalog standards those roles used
(see get_household_preferences). It never edits the dish/recipe/task content itself - only
these record_* calls, which set `score` (0-100) and `audit_feedback` (free text) on the
row being judged.
"""

from __future__ import annotations

from typing import Any

from .registry import tool
from .weekly_plan import parse_weekly_plan_row
from ..db import connect, fetch_record


@tool
def get_unaudited_weekly_menu_items() -> list[dict[str, Any]]:
    """Weekly menu rows the Food Inspector has not yet scored (score IS NULL).

    A row's score/audit_feedback is cleared back to NULL whenever the Executive Chef
    re-saves that slot with a changed dish, so this always reflects the latest decision
    still awaiting judgement.
    """
    with connect() as connection:
        return [
            dict(row)
            for row in connection.execute("SELECT * FROM weekly_menu WHERE score IS NULL ORDER BY id")
        ]


@tool
def record_weekly_menu_audit(weekly_menu_id: int, score: int, audit_feedback: str) -> dict[str, Any]:
    """Record the Food Inspector's judgement of one saved weekly_menu row.

    score: 0-100, judged against the same household dietary/macro rules and
    get_household_preferences context (favourites, chef note, household members'
    dietary preferences and health conditions) the Executive Chef used to plan it.
    audit_feedback: a short written explanation of the score - what the dish gets right
    and, if the score is not perfect, exactly what rule or preference it falls short on.
    """
    if not 0 <= score <= 100:
        raise ValueError("score must be between 0 and 100")
    with connect() as connection:
        cursor = connection.execute(
            "UPDATE weekly_menu SET score = ?, audit_feedback = ? WHERE id = ?",
            (score, audit_feedback.strip(), weekly_menu_id),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"No weekly_menu record found for id {weekly_menu_id}")
    return fetch_record("weekly_menu", weekly_menu_id)


@tool
def get_unaudited_prep_tasks() -> list[dict[str, Any]]:
    """Prep-schedule rows the Food Inspector has not yet scored (score IS NULL).

    Includes cancelled tasks - the Sous Chef's decision at creation time is what's being
    judged, not whether the task was later performed.
    """
    with connect() as connection:
        return [
            dict(row)
            for row in connection.execute("SELECT * FROM detailed_prep_schedule WHERE score IS NULL ORDER BY id")
        ]


@tool
def record_prep_task_audit(prep_schedule_id: int, score: int, audit_feedback: str) -> dict[str, Any]:
    """Record the Food Inspector's judgement of one saved detailed_prep_schedule row.

    score: 0-100, judged against the same household dietary/macro rules and
    get_household_preferences context the Sous Chef used when deciding the instructions
    and ingredients_used.
    audit_feedback: a short written explanation of the score.
    """
    if not 0 <= score <= 100:
        raise ValueError("score must be between 0 and 100")
    with connect() as connection:
        cursor = connection.execute(
            "UPDATE detailed_prep_schedule SET score = ?, audit_feedback = ? WHERE id = ?",
            (score, audit_feedback.strip(), prep_schedule_id),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"No detailed_prep_schedule record found for id {prep_schedule_id}")
    return fetch_record("detailed_prep_schedule", prep_schedule_id)


@tool
def get_unaudited_weekly_plans() -> list[dict[str, Any]]:
    """Weekly-plan rows the Food Inspector has not yet scored (score IS NULL).

    Each row is one planned week (see weekly_plans); a row is created/upserted
    automatically whenever the weekly_menu job completes, so this reflects whichever
    weeks still need a whole-plan judgement. Each row carries its own
    skip_meals_snapshot/chef_note_snapshot/restrictions_snapshot - the exact household
    context the Executive Chef planned this week under - use those to judge the week,
    not a fresh get_household_preferences call (the live config may have changed since).
    """
    with connect() as connection:
        return [
            parse_weekly_plan_row(dict(row))
            for row in connection.execute("SELECT * FROM weekly_plans WHERE score IS NULL ORDER BY id")
        ]


@tool
def record_weekly_plan_audit(weekly_plan_id: int, score: int, audit_feedback: str) -> dict[str, Any]:
    """Record the Food Inspector's judgement of one week's overall plan.

    Judge against the row's own snapshot (get_unaudited_weekly_plans), not a fresh
    get_household_preferences call: completeness (every slot skip_meals_snapshot didn't
    exclude has a saved dish - call get_weekly_menu for the full saved week first),
    restrictions_snapshot's "week"-scope entries (e.g. lunch variety), and whether the
    week reflects chef_note_snapshot when it is non-empty. score: 0-100. audit_feedback:
    a short written explanation - what the week's plan gets right and, if the score is
    not perfect, exactly what it falls short on (a missing slot, an unmet restriction, or
    an ignored chef note).
    """
    if not 0 <= score <= 100:
        raise ValueError("score must be between 0 and 100")
    with connect() as connection:
        cursor = connection.execute(
            "UPDATE weekly_plans SET score = ?, audit_feedback = ? WHERE id = ?",
            (score, audit_feedback.strip(), weekly_plan_id),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"No weekly_plans record found for id {weekly_plan_id}")
    return parse_weekly_plan_row(fetch_record("weekly_plans", weekly_plan_id))


@tool
def get_unaudited_recipes() -> list[dict[str, Any]]:
    """Recipe catalog rows the Food Inspector has not yet scored (score IS NULL).

    A recipe's score/audit_feedback is cleared back to NULL whenever the Executive Chef
    (or a household member's "identify tags"/"recreate instructions" request) saves a
    change to it via update_recipe, so this always reflects the latest content still
    awaiting judgement.
    """
    with connect() as connection:
        return [
            dict(row)
            for row in connection.execute("SELECT * FROM recipes WHERE score IS NULL ORDER BY id")
        ]


@tool
def record_recipe_audit(recipe_id: int, score: int, audit_feedback: str) -> dict[str, Any]:
    """Record the Food Inspector's judgement of one recipe catalog row.

    score: 0-100, judged against the household's recipe catalog standards - are the tags
    accurate and complete (diet category stated explicitly, both positive and negative;
    allergen/nutrition labels present where the ingredients/macros support them), and are
    the instructions clear, ordered, and complete.
    audit_feedback: a short written explanation of the score - what the recipe gets right
    and, if the score is not perfect, exactly what tag or instruction issue it falls
    short on.
    """
    if not 0 <= score <= 100:
        raise ValueError("score must be between 0 and 100")
    with connect() as connection:
        cursor = connection.execute(
            "UPDATE recipes SET score = ?, audit_feedback = ? WHERE id = ?",
            (score, audit_feedback.strip(), recipe_id),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"No recipes record found for id {recipe_id}")
    return fetch_record("recipes", recipe_id)
