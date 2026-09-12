"""Food Inspector data operations: find unaudited rows, record a score + feedback.

The Food Inspector is an LLM-as-judge role that evaluates decisions the Executive Chef
(weekly_menu) and Sous Chef (detailed_prep_schedule) already made, against the same
household rules/preferences/conditions those roles used (see get_household_preferences).
It never edits the dish/task content itself - only these two record_* calls, which set
`score` (0-100) and `audit_feedback` (free text) on the row being judged.
"""

from __future__ import annotations

from typing import Any

from .registry import tool
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
