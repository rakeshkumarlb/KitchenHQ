"""Fetch the stored data an email needs when the agent omits it from the payload:
the saved weekly menu (for `send_weekly_plan_email` without `days`) and the pending
shopping items (for `send_shopping_list_email` without `items`).

Both come from dbmcp's `GET /api/dashboard` - the agent never touches the DB directly.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..config import Settings

logger = logging.getLogger("kitchenhq-agent")

_WEEKDAY_ORDER = {day: i for i, day in enumerate(
    ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
)}
_MEAL_ORDER = {"breakfast": 0, "lunch": 1, "snack": 2, "dinner": 3}


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
        logger.warning("Could not fetch dashboard for email back-fill", exc_info=True)
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


def fetch_shopping_items(settings: Settings) -> list[dict[str, Any]]:
    """The currently pending shopping items, shaped for the email schema."""
    return [
        {
            "item_name": item.get("item_name", ""),
            "proposed_quantity": item.get("proposed_quantity", 0),
            "unit": item.get("unit", ""),
            "reason": "",
        }
        for item in _dashboard(settings).get("shopping_items") or []
    ]
