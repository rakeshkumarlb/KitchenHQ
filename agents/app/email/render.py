"""Body builders: (payload dict, greeting) -> (subject, text_body, html_body).

Presentation only - no network, no config. `parse_lines` turns a weekly_menu
ingredients / full_recipe value (a JSON string array, or legacy free text) into a
clean list of lines for both the plain-text and HTML parts.
"""

from __future__ import annotations

import json
import re
from html import escape
from typing import Any

from ..constants import DAY_ORDER as _WEEKDAY_ORDER, MEAL_TYPE_ORDER as _MEAL_ORDER

_ENUM_PREFIX = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+")


def parse_lines(value: Any) -> list[str]:
    """Normalize a stored ingredients/recipe value into a list of plain-text lines.

    Accepts a real list, a JSON-array string (the current format), or legacy free text
    (comma-joined ingredients / newline-joined "1. step" recipe blobs).
    """
    if isinstance(value, list):
        raw = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            raw = parsed if isinstance(parsed, list) else _legacy_split(text)
        except (json.JSONDecodeError, ValueError):
            raw = _legacy_split(text)
    else:
        return []
    lines = []
    for item in raw:
        line = _ENUM_PREFIX.sub("", str(item).strip()).strip()
        if line:
            lines.append(line)
    return lines


def _legacy_split(text: str) -> list[str]:
    parts = [p.strip() for p in text.splitlines() if p.strip()]
    if len(parts) <= 1:
        parts = [p.strip() for p in text.split(",") if p.strip()]
    return parts


# --- shared HTML scaffolding -----------------------------------------------------

def _doc(*sections: str) -> str:
    body = "\n".join(s for s in sections if s)
    return (
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'font-size:14px;line-height:1.6;color:#29312e;max-width:640px">'
        f"{body}</div>"
    )


def _h(text: str) -> str:
    return f'<h2 style="font-size:15px;margin:22px 0 8px;color:#274538">{escape(text)}</h2>'


def _ul(lines: list[str], ordered: bool = False) -> str:
    if not lines:
        return ""
    tag = "ol" if ordered else "ul"
    items = "".join(f"<li>{escape(line)}</li>" for line in lines)
    return f'<{tag} style="margin:6px 0;padding-left:22px">{items}</{tag}>'


def _p(text: str) -> str:
    return f"<p>{escape(text)}</p>"


# --- format 1: prep task -------------------------------------------------------

def build_prep_task_email(data: dict[str, Any], greeting: str) -> tuple[str, str, str]:
    meals = data.get("meals") or []
    meal_summary = "; ".join(
        f"{m['dish']} ({m['meal_type']}, {m['servings']} {'person' if m['servings'] == 1 else 'people'})"
        for m in meals
    )
    prep_date = data.get("prep_date", "today")
    subject = f"[KitchenHQ] Prep plan for {prep_date} - {meal_summary or 'kitchen prep'}"
    steps = list(data.get("steps") or [])
    ingredients = list(data.get("ingredients") or [])
    meal_lines = [
        f"{m['dish']} - {m['meal_type']}, for {m['servings']} {'person' if m['servings'] == 1 else 'people'}"
        for m in meals
    ]

    text_lines = [
        greeting, "", f"Date: {data.get('prep_date', '')}", "",
        "Preparing today:", *[f"  - {line}" for line in meal_lines], "",
        "Steps:", *[f"  {i}. {step}" for i, step in enumerate(steps, start=1)], "",
        "Ingredients you'll use:", *[f"  - {line}" for line in ingredients],
    ]
    if data.get("notes"):
        text_lines += ["", "Notes:", f"  {data['notes']}"]
    text_lines += ["", "Open KitchenHQ to check the task off when it's done.", ""]

    html = _doc(
        _p(greeting),
        _p(f"Prep plan for {prep_date}."),
        _h("Preparing"), _ul(meal_lines),
        _h("Steps"), _ul(steps, ordered=True),
        _h("Ingredients you'll use"), _ul(ingredients),
        (_h("Notes") + _p(data["notes"])) if data.get("notes") else "",
        _p("Open KitchenHQ to check the task off when it's done."),
    )
    return subject, "\n".join(text_lines), html


# --- format 2: weekly plan ---------------------------------------------------

def build_weekly_plan_email(data: dict[str, Any], greeting: str) -> tuple[str, str, str]:
    week_start, week_end = data.get("week_start", ""), data.get("week_end", "")
    subject = f"[KitchenHQ] Weekly menu {week_start} to {week_end}".strip()
    days = _sorted_days(data.get("days") or [])
    considerations = list(data.get("considerations") or [])
    shopping_needs = list(data.get("shopping_needs") or [])

    text_lines = [greeting, "", f"Here is the plan for {week_start} - {week_end}.", "", "THE WEEK", "========"]
    day_blocks_html = []
    for day in days:
        text_lines.append("")
        text_lines.append(str(day.get("day_of_week", "")).capitalize())
        meal_items_html = []
        for meal in _sorted_meals(day.get("meals") or []):
            head = f"{meal['meal_type']}: {meal['dish']}"
            if meal.get("macros"):
                head += f"  [{meal['macros']}]"
            text_lines.append(f"  - {head}")
            ing = parse_lines(meal.get("ingredients"))
            for line in ing:
                text_lines.append(f"      - {line}")
            meal_items_html.append(f"<li><strong>{escape(head)}</strong>{_ul(ing)}</li>")
        day_blocks_html.append(
            f'<h3 style="font-size:14px;margin:16px 0 4px">{escape(str(day.get("day_of_week", "")).capitalize())}</h3>'
            f'<ul style="margin:4px 0;padding-left:22px">{"".join(meal_items_html)}</ul>'
        )

    text_lines += ["", "CONSIDERATIONS", "=============="]
    text_lines += [f"  - {c}" for c in considerations]
    if shopping_needs:
        text_lines += ["", "INGREDIENTS WE MAY NEED", "======================="]
        text_lines += [f"  - {s}" for s in shopping_needs]
    if data.get("notes"):
        text_lines += ["", "Notes:", f"  {data['notes']}"]
    text_lines += ["", "Open KitchenHQ to review or rate the week.", ""]

    html = _doc(
        _p(greeting),
        _p(f"Here is the plan for {week_start} - {week_end}."),
        _h("The week"), "".join(day_blocks_html),
        _h("Considerations"), _ul(considerations),
        (_h("Ingredients we may need") + _ul(shopping_needs)) if shopping_needs else "",
        (_h("Notes") + _p(data["notes"])) if data.get("notes") else "",
        _p("Open KitchenHQ to review or rate the week."),
    )
    return subject, "\n".join(text_lines), html


def _sorted_days(days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(days, key=lambda d: _WEEKDAY_ORDER.get(str(d.get("day_of_week", "")).lower(), 99))


def _sorted_meals(meals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(meals, key=lambda m: _MEAL_ORDER.get(str(m.get("meal_type", "")).lower(), 99))


# --- format 3: shopping list -----------------------------------------------

def build_shopping_list_email(data: dict[str, Any], greeting: str) -> tuple[str, str, str]:
    items = data.get("items") or []
    reasoning = list(data.get("reasoning") or [])
    subject = f"[KitchenHQ] Shopping suggestions ({len(items)} item{'s' if len(items) != 1 else ''})"

    item_lines = []
    for item in items:
        line = f"{item['item_name']}: {item['proposed_quantity']} {item['unit']}"
        if item.get("reason"):
            line += f"  ({item['reason']})"
        item_lines.append(line)

    text_lines = [greeting, ""]
    text_lines += ["SUGGESTED ITEMS", "==============="]
    text_lines += [f"  - {line}" for line in item_lines]
    text_lines += ["", "REASONING", "========="]
    text_lines += [f"  - {r}" for r in reasoning]
    if data.get("notes"):
        text_lines += ["", "Notes:", f"  {data['notes']}"]
    text_lines += ["", "Open KitchenHQ to review and acknowledge the shopping run.", ""]

    html = _doc(
        _p(greeting),
        _h("Suggested items"), _ul(item_lines),
        _h("Reasoning"), _ul(reasoning),
        (_h("Notes") + _p(data["notes"])) if data.get("notes") else "",
        _p("Open KitchenHQ to review and acknowledge the shopping run."),
    )
    return subject, "\n".join(text_lines), html
