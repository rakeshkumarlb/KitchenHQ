"""Deterministic weekly_menu/weekly_plans record-keeping - never an LLM tool call.

Right after a successful `weekly_menu` job, `jobs.py::run_job` already knows that
week's start/end dates (from `job_context.build_job_context`'s `target_menu_days`,
resolved without any LLM involvement) and the skip_meals/chef-note/restrictions config it
just planned around. `record_weekly_plan` posts that to dbmcp's `POST /api/weekly-plans`,
the same best-effort REST-after-job-completion shape `telemetry.py::record_agent_run`
already uses - so the Food Inspector's `weekly_plan_audit` job always has a row to judge,
with no risk of the Executive Chef forgetting to save one itself.

`record_skipped_menu_slots` posts the same run's skip_meals slots to dbmcp's
`POST /api/weekly-menu/skip`, for the same reason: the Executive Chef is told not to call
add_weekly_menu_item for a skipped slot, so without a deterministic placeholder that slot
would keep showing whatever dish an earlier week last saved there.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import Settings

logger = logging.getLogger("kitchenhq-agent")


async def record_weekly_plan(
    settings: Settings,
    week_start_date: str,
    week_end_date: str,
    skip_meals_snapshot: dict[str, list[str]],
    chef_note_snapshot: str = "",
    restrictions_snapshot: list[dict[str, Any]] | None = None,
) -> None:
    """Best-effort; a telemetry-adjacent write must not fail the weekly_menu job itself."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(
                f"{settings.db_api_url}/api/weekly-plans",
                json={
                    "week_start_date": week_start_date,
                    "week_end_date": week_end_date,
                    "skip_meals_snapshot": skip_meals_snapshot,
                    "chef_note_snapshot": chef_note_snapshot,
                    "restrictions_snapshot": restrictions_snapshot or [],
                },
                headers={"X-API-Key": settings.kitchenhq_api_key},
            )
            response.raise_for_status()
    except Exception:
        logger.warning("Could not record weekly_plans row for %s..%s", week_start_date, week_end_date, exc_info=True)


async def record_skipped_menu_slots(settings: Settings, slots: list[tuple[str, str]]) -> None:
    """Best-effort; a placeholder write must not fail the weekly_menu job itself."""
    if not slots:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(
                f"{settings.db_api_url}/api/weekly-menu/skip",
                json={"slots": [{"day_of_week": day, "meal_type": meal} for day, meal in slots]},
                headers={"X-API-Key": settings.kitchenhq_api_key},
            )
            response.raise_for_status()
    except Exception:
        logger.warning("Could not record %d skipped weekly_menu slot(s)", len(slots), exc_info=True)
