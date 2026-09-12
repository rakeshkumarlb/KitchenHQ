"""Wire the three email tools the agent gets each run: validate the payload, render it,
send it. The agent passes the plan/list it just authored; only send_weekly_plan_email
falls back to reading the saved menu (when `days` is omitted). Tool names and
parameters match the send_*_email MCP tools they replaced.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ValidationError

from ..config import Settings
from . import backfill, render
from .schemas import PrepTaskEmailRequest, ShoppingListEmailRequest, WeeklyPlanEmailRequest
from .smtp import greeting, send_email


def _validated(model: type[BaseModel], payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return model.model_validate(payload).model_dump()
    except ValidationError as error:
        raise ValueError(f"Invalid email payload: {error}") from error


def make_email_tools(settings: Settings) -> list[StructuredTool]:
    """Three StructuredTools bound to this run's settings, appended to the toolset by
    `kitchen_agent.run_agent` (like `get_job_context`)."""

    def send_prep_task_email(
        prep_date: str,
        meals: list[dict[str, Any]],
        steps: list[str],
        ingredients: list[str],
        notes: str = "",
    ) -> dict[str, Any]:
        """Email the household the prep/cooking plan for a human to execute (Sous Chef).

        Send this whenever you save a prep schedule - on a scheduled prep job or when a
        chat user asks for a prep/cooking plan. Include:
          - prep_date: the date this prep is for (get it from get_job_context)
          - meals: [{dish, meal_type, servings}] - the meal(s) being prepared and for how
            many people (household size comes from get_household_preferences' household_members)
          - steps: the ordered, detailed steps to perform
          - ingredients: the ingredients that will be used
        Returns {"sent": bool, ...}; a missing mailbox is reported, not an error.
        """
        data = _validated(
            PrepTaskEmailRequest,
            {"prep_date": prep_date, "meals": meals, "steps": steps, "ingredients": ingredients, "notes": notes},
        )
        subject, text, html = render.build_prep_task_email(data, greeting(settings))
        return send_email(subject, text, html, settings=settings)

    def send_weekly_plan_email(
        week_start: str,
        week_end: str,
        considerations: list[str],
        shopping_needs: list[str] | None = None,
        days: list[dict[str, Any]] | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        """Email the household the weekly menu with the thinking behind it (Executive Chef).

        Send this every time you finish saving a weekly menu. You only need:
          - week_start / week_end: the Monday and Sunday dates the week covers
          - considerations: your reasoning - favourites reused, how the dietary/macro rules
            were satisfied, inventory gaps
          - shopping_needs: the ingredients you'll likely need to buy, in detail
        `days` is optional - leave it out and the saved weekly_menu is used, so you don't
        have to restate the week. Returns {"sent": bool, ...}; a missing mailbox is
        reported, not raised.
        """
        data = _validated(
            WeeklyPlanEmailRequest,
            {
                "week_start": week_start,
                "week_end": week_end,
                "days": days or [],
                "considerations": considerations,
                "shopping_needs": shopping_needs or [],
                "notes": notes,
            },
        )
        if not data["days"]:
            data["days"] = backfill.fetch_weekly_menu_days(settings)
        if not data["days"]:
            return {"sent": False, "skipped": "no weekly menu is saved to email"}
        subject, text, html = render.build_weekly_plan_email(data, greeting(settings))
        return send_email(subject, text, html, settings=settings)

    def send_shopping_list_email(
        reasoning: list[str],
        items: list[dict[str, Any]],
        notes: str = "",
    ) -> dict[str, Any]:
        """Email the household the shopping suggestions and why (Pantry Manager).

        Send this whenever you finish adding to the shopping list. Pass:
          - items: the shopping items you just added - [{item_name, proposed_quantity,
            unit, reason}], a short reason each (in a chat, read them back with
            get_shopping_items first)
          - reasoning: the overall rationale (what's below threshold, what the upcoming
            menu needs)
        Returns {"sent": bool, ...}; a missing mailbox is reported, not raised.
        """
        data = _validated(ShoppingListEmailRequest, {"items": items, "reasoning": reasoning, "notes": notes})
        subject, text, html = render.build_shopping_list_email(data, greeting(settings))
        return send_email(subject, text, html, settings=settings)

    return [
        StructuredTool.from_function(func=send_prep_task_email),
        StructuredTool.from_function(func=send_weekly_plan_email),
        StructuredTool.from_function(func=send_shopping_list_email),
    ]
