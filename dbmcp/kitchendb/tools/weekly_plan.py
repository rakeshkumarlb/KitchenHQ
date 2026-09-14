"""Weekly-plan record keeping.

`upsert_weekly_plan` is REST-only (no `@tool` decorator, like `acknowledge_shopping_items`
in shopping.py) - it's called deterministically by agent-api's `run_job` right after a
successful `weekly_menu` job completion (mirroring how `agent_runs` telemetry is posted),
never by an LLM. The Food Inspector's own read/write pair for scoring these rows -
`get_unaudited_weekly_plans`/`record_weekly_plan_audit` - lives in `audit.py` alongside
its other audit tools.
"""

from __future__ import annotations

import json
from typing import Any

from .registry import tool
from ..db import connect


def _parse_json(raw: Any, default: Any) -> Any:
    try:
        value = json.loads(raw) if raw is not None else default
    except (json.JSONDecodeError, TypeError):
        return default
    return value if isinstance(value, type(default)) else default


def parse_weekly_plan_row(row: dict[str, Any]) -> dict[str, Any]:
    """Turn the JSON-text snapshot columns back into native objects for callers."""
    row["skip_meals_snapshot"] = _parse_json(row.get("skip_meals_snapshot"), {})
    row["restrictions_snapshot"] = _parse_json(row.get("restrictions_snapshot"), [])
    return row


def upsert_weekly_plan(
    week_start_date: str,
    week_end_date: str,
    skip_meals_snapshot: dict[str, list[str]],
    chef_note_snapshot: str = "",
    restrictions_snapshot: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create or replace the weekly_plans row for this week (keyed by week_start_date).

    skip_meals_snapshot/chef_note_snapshot/restrictions_snapshot (the latter already
    filtered to enabled: true) capture the exact household context the Executive Chef
    planned this week under, so the Food Inspector's weekly_plan_audit judges against
    what was true then rather than whatever get_household_preferences returns tonight.
    A re-plan of the same week resets score/audit_feedback to NULL - a new plan is a new
    decision awaiting the Food Inspector's judgement, same convention as weekly_menu.
    """
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO weekly_plans (
                week_start_date, week_end_date, skip_meals_snapshot,
                chef_note_snapshot, restrictions_snapshot, score, audit_feedback, updated_at
            )
            VALUES (?, ?, ?, ?, ?, NULL, NULL, CURRENT_TIMESTAMP)
            ON CONFLICT(week_start_date) DO UPDATE SET
                week_end_date = excluded.week_end_date,
                skip_meals_snapshot = excluded.skip_meals_snapshot,
                chef_note_snapshot = excluded.chef_note_snapshot,
                restrictions_snapshot = excluded.restrictions_snapshot,
                score = NULL,
                audit_feedback = NULL,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                week_start_date,
                week_end_date,
                json.dumps(skip_meals_snapshot),
                str(chef_note_snapshot or "").strip(),
                json.dumps(restrictions_snapshot or []),
            ),
        )
        row = connection.execute(
            "SELECT * FROM weekly_plans WHERE week_start_date = ?", (week_start_date,)
        ).fetchone()
    return parse_weekly_plan_row(dict(row))


@tool
def get_weekly_plans() -> list[dict[str, Any]]:
    """Read every saved weekly plan (start/end dates, snapshot of the context it was planned under, audit score)."""
    with connect() as connection:
        return [
            parse_weekly_plan_row(dict(row))
            for row in connection.execute("SELECT * FROM weekly_plans ORDER BY week_start_date DESC")
        ]
