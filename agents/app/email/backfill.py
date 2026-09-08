"""Fetch the saved weekly menu for ``send_weekly_plan_email`` when the agent omits
``days``.

That email summarizes a whole week and sending it is not an enforced job step, so it
is built from dbmcp's stored menu (``GET /api/dashboard``) rather than trusting the
model to re-emit all 28 slots. The prep and shopping-list emails carry data the agent
authored in the same run, so they have no back-fill - the agent passes it in the call.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..config import Settings
from ..constants import DAY_ORDER as _WEEKDAY_ORDER, MEAL_TYPE_ORDER as _MEAL_ORDER

logger = logging.getLogger("kitchenhq-agent")


def _dashboard(settings: Settings) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=10) as client:
            response = client.get(
                f"{settings.db_api_url}/api/dashboard",
                headers={"X-API-Key": settings.kitchenhq_api_key},
            )
            response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        logger.warning("Could not fetch dashboard for weekly-plan email back-fill", exc_info=True)
        return {}


def fetch_weekly_menu_days(settings: Settings) -> list[dict[str, Any]]:
    """The saved menu as [{day_of_week, meals:[{meal_type, dish, macros, ingredients}]}]."""
    rows = _dashboard(settings).get("menu") or []
    by_day: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_day.setdefault(str(row.get("day_of_week", "")).lower(), []).append({
            "meal_type": str(row.get("meal_type", "")).lower(),
            "dish": row.get("dish_name", ""),
            "macros": row.get("macros") or "",
            "ingredients": row.get("ingredients") or "",
        })
    days = []
    for day in sorted(by_day, key=lambda d: _WEEKDAY_ORDER.get(d, 99)):
        meals = sorted(by_day[day], key=lambda m: _MEAL_ORDER.get(m["meal_type"], 99))
        days.append({"day_of_week": day, "meals": meals})
    return days
