"""The REST surface: one thin route per data operation, plus /api/health and
/api/dashboard.

Every route either reads directly or unpacks a Pydantic model and calls the matching
function in kitchendb/tools/. A ValueError from a data operation becomes HTTP 400.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from constants import DAY_ORDER, DAYS, MEAL_TYPE_ORDER, MEAL_TYPES, day_case_sql, meal_case_sql
from tags import TAG_CATEGORIES

from .db import connect, fetch_record_in
from .models import (
    AgentRunRequest,
    ChatSessionRequest,
    HouseholdMemberRequest,
    HouseholdMemberUpdateRequest,
    InventoryAddRequest,
    InventoryAdjustmentRequest,
    InventoryDiscardRequest,
    MenuItemRequest,
    MenuSkipRequest,
    PrepCancellationRequest,
    PrepCompletionRequest,
    PrepScheduleRequest,
    ProfileUpdateRequest,
    RecipeRatingRequest,
    RecipeRequest,
    ShoppingAcknowledgementRequest,
    ShoppingItemEditRequest,
    ShoppingItemsRequest,
    WeeklyPlanRequest,
)
from .tools.inventory import add_inventory, adjust_inventory_quantity, remove_or_discard_inventory
from .tools.prep import add_detailed_prep_schedule, cancel_prep_schedule, capture_prep_completion_status
from .tools.profile import (
    add_household_member,
    delete_household_member,
    get_user_profile,
    list_household_members,
    update_household_member,
    update_user_profile,
)
from .tools.shopping import (
    acknowledge_shopping_items,
    add_shopping_items,
    clear_shopping_items,
    delete_shopping_item,
    edit_shopping_item,
    get_shopping_items,
)
from .tools.recipes import (
    add_recipe,
    delete_recipe,
    get_recipe,
    list_recipes,
    rate_recipe,
    search_recipes,
    update_recipe,
)
from .tools.weekly_menu import add_weekly_menu_item, mark_weekly_menu_skipped
from .tools.weekly_plan import get_weekly_plans, upsert_weekly_plan

router = APIRouter()

_MENU_ORDER = f"{day_case_sql()}, {meal_case_sql()}, id"


def _tool_error(error: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(error))


@router.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ready"}


@router.get("/api/dashboard")
def dashboard() -> dict[str, Any]:
    with connect() as connection:
        return {
            "inventory": [dict(row) for row in connection.execute("SELECT * FROM inventory ORDER BY category, item_name")],
            "menu": [dict(row) for row in connection.execute(f"SELECT * FROM weekly_menu ORDER BY {_MENU_ORDER}")],
            "tasks": [dict(row) for row in connection.execute(
                "SELECT * FROM detailed_prep_schedule WHERE status <> 'cancelled' AND (is_completed = 0 OR id IN (SELECT id FROM detailed_prep_schedule WHERE is_completed = 1 AND status <> 'cancelled' ORDER BY id DESC LIMIT 10)) ORDER BY is_completed, id"
            )],
            "shopping_items": [dict(row) for row in connection.execute("SELECT * FROM shopping_items ORDER BY item_name")],
            "consumption": [dict(row) for row in connection.execute(
                """
                SELECT i.id AS inventory_id, i.item_name, i.unit,
                       ROUND(SUM(-t.quantity_change), 3) AS quantity_consumed,
                       COUNT(*) AS transaction_count,
                       MAX(t.created_at) AS last_consumed_at
                FROM inventory_transactions t
                JOIN inventory i ON i.id = t.inventory_id
                WHERE t.quantity_change < 0
                  AND t.created_at >= datetime('now', '-7 days')
                GROUP BY t.inventory_id
                ORDER BY quantity_consumed DESC, i.item_name
                """
            )],
            "profile": _dashboard_profile(connection),
            "household_members": [
                {**dict(row), "dietary_preferences": json.loads(row["dietary_preferences"]), "health_conditions": json.loads(row["health_conditions"])}
                for row in connection.execute("SELECT * FROM household_members ORDER BY id")
            ],
            "weekly_plans": get_weekly_plans(),
            "recipe_count": connection.execute("SELECT COUNT(*) FROM recipes").fetchone()[0],
            # Day / meal / tag vocabulary for non-Python clients (the chatui React app) -
            # the single source of truth is shared/constants.py and shared/tags.py,
            # vendored here as constants.py and tags.py.
            "constants": {
                "days": list(DAYS),
                "meal_types": list(MEAL_TYPES),
                "day_order": DAY_ORDER,
                "meal_type_order": MEAL_TYPE_ORDER,
                "tags": [{"category": category, "tags": list(tags)} for category, tags in TAG_CATEGORIES],
            },
        }


def _dashboard_profile(connection) -> dict[str, Any]:
    row = connection.execute("SELECT * FROM user_profile WHERE id = 1").fetchone()
    if row is None:
        return {}
    profile = dict(row)
    # favorite_recipes is legacy and stays a raw JSON string (existing chatui precedent);
    # the newer preference fields are parsed server-side into native JSON, same treatment
    # household_members already gets for dietary_preferences/health_conditions.
    for field, default in (("restrictions", "[]"), ("skip_meals", "{}"), ("preferred_tags", "[]"), ("excluded_tags", "[]")):
        profile[field] = json.loads(profile.get(field) or default)
    return profile


@router.post("/api/inventory")
def api_add_inventory(request: InventoryAddRequest) -> dict[str, Any]:
    try:
        return add_inventory(**request.model_dump())
    except ValueError as error:
        raise _tool_error(error) from error


@router.patch("/api/inventory/{item_id}")
def api_adjust_inventory(item_id: int, request: InventoryAdjustmentRequest) -> dict[str, Any]:
    try:
        return adjust_inventory_quantity(item_id, request.quantity_change)
    except ValueError as error:
        raise _tool_error(error) from error


@router.post("/api/inventory/{item_id}/discard")
def api_discard_inventory(item_id: int, request: InventoryDiscardRequest) -> dict[str, Any]:
    try:
        return remove_or_discard_inventory(item_id, **request.model_dump())
    except ValueError as error:
        raise _tool_error(error) from error


@router.post("/api/weekly-menu")
def api_add_menu_item(request: MenuItemRequest) -> dict[str, Any]:
    try:
        return add_weekly_menu_item(**request.model_dump())
    except ValueError as error:
        raise _tool_error(error) from error


@router.post("/api/weekly-menu/skip")
def api_skip_menu_slots(request: MenuSkipRequest) -> list[dict[str, Any]]:
    # Code-triggered only (agent-api's run_job, right after a successful weekly_menu job)
    # - writes a placeholder for every slot that job's skip_meals config excluded, so a
    # dish saved for that slot in an earlier week stops showing as if still planned.
    try:
        return mark_weekly_menu_skipped([slot.model_dump() for slot in request.slots])
    except ValueError as error:
        raise _tool_error(error) from error


@router.get("/api/weekly-plans")
def api_get_weekly_plans() -> list[dict[str, Any]]:
    return get_weekly_plans()


@router.post("/api/weekly-plans")
def api_upsert_weekly_plan(request: WeeklyPlanRequest) -> dict[str, Any]:
    # Code-triggered only (agent-api's run_job, right after a successful weekly_menu job)
    # - never called by an LLM, so no ValueError->400 translation needed beyond Pydantic's.
    return upsert_weekly_plan(**request.model_dump())


@router.post("/api/prep-schedule")
def api_add_prep_schedule(request: PrepScheduleRequest) -> dict[str, Any]:
    try:
        return add_detailed_prep_schedule(**request.model_dump())
    except ValueError as error:
        raise _tool_error(error) from error


@router.patch("/api/prep-schedule/{prep_schedule_id}/completion")
def api_capture_completion(prep_schedule_id: int, request: PrepCompletionRequest) -> dict[str, Any]:
    try:
        return capture_prep_completion_status(prep_schedule_id, **request.model_dump())
    except ValueError as error:
        raise _tool_error(error) from error


@router.post("/api/prep-schedule/{prep_schedule_id}/cancel")
def api_cancel_prep(prep_schedule_id: int, request: PrepCancellationRequest) -> dict[str, Any]:
    try:
        return cancel_prep_schedule(prep_schedule_id, **request.model_dump())
    except ValueError as error:
        raise _tool_error(error) from error


@router.get("/api/shopping-items")
def api_get_shopping_items() -> list[dict[str, Any]]:
    return get_shopping_items()


@router.post("/api/shopping-items")
def api_add_shopping_items(request: ShoppingItemsRequest) -> list[dict[str, Any]]:
    try:
        return add_shopping_items([item.model_dump() for item in request.items])
    except ValueError as error:
        raise _tool_error(error) from error


@router.patch("/api/shopping-items/{shopping_item_id}")
def api_edit_shopping_item(shopping_item_id: int, request: ShoppingItemEditRequest) -> dict[str, Any]:
    try:
        return edit_shopping_item(shopping_item_id, **request.model_dump())
    except ValueError as error:
        raise _tool_error(error) from error


@router.delete("/api/shopping-items/{shopping_item_id}")
def api_delete_shopping_item(shopping_item_id: int) -> dict[str, Any]:
    try:
        return delete_shopping_item(shopping_item_id)
    except ValueError as error:
        raise _tool_error(error) from error


@router.post("/api/shopping-items/clear")
def api_clear_shopping_items() -> dict[str, Any]:
    return clear_shopping_items()


@router.post("/api/shopping-items/acknowledge")
def api_acknowledge_shopping(request: ShoppingAcknowledgementRequest) -> dict[str, Any]:
    try:
        return acknowledge_shopping_items(**request.model_dump())
    except ValueError as error:
        raise _tool_error(error) from error


@router.post("/api/agent-runs")
def api_record_agent_run(request: AgentRunRequest) -> dict[str, Any]:
    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO agent_runs (agent_role, job_name, status, result, error, context_length, input_tokens, output_tokens, total_tokens) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                request.agent_role, request.job_name, request.status, request.result, request.error,
                request.context_length, request.input_tokens, request.output_tokens, request.total_tokens,
            ),
        )
        return fetch_record_in(connection, "agent_runs", cursor.lastrowid)


@router.get("/api/agent-runs")
def api_agent_runs(limit: int = Query(100, ge=1, le=500)) -> list[dict[str, Any]]:
    with connect() as connection:
        return [
            dict(row)
            for row in connection.execute("SELECT * FROM agent_runs ORDER BY id DESC LIMIT ?", (limit,))
        ]


@router.get("/api/agent-runs/usage-summary")
def api_agent_runs_usage_summary(days: int = Query(7, ge=1, le=90)) -> list[dict[str, Any]]:
    """Daywise usage totals for the last `days` days (oldest first), grouped by the
    calendar date agent_runs.started_at falls on. Days with zero runs are omitted -
    the caller fills gaps if it wants a complete date axis."""
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT
                date(started_at) AS day,
                COUNT(*) AS total_runs,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_runs,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_runs,
                COALESCE(SUM(input_tokens), 0) AS input_tokens,
                COALESCE(SUM(output_tokens), 0) AS output_tokens,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                MAX(context_length) AS max_context_length
            FROM agent_runs
            WHERE started_at >= date('now', ?)
            GROUP BY day
            ORDER BY day ASC
            """,
            (f"-{days - 1} days",),
        )
        return [dict(row) for row in rows]


_USAGE_METRICS = ("context_length", "input_tokens", "output_tokens", "total_tokens")


def _usage_stats(connection, where: str = "", params: tuple[Any, ...] = ()) -> dict[str, dict[str, Any]]:
    """MIN/MAX/AVG/COUNT for each usage metric over the rows `where` selects. SQLite's
    aggregate functions already skip NULLs (a run whose provider never reported
    usage_metadata), so `count` is how many runs actually had a value, not the row total."""
    select_parts = ", ".join(
        f"MIN({metric}) AS {metric}_min, MAX({metric}) AS {metric}_max, "
        f"AVG({metric}) AS {metric}_avg, COUNT({metric}) AS {metric}_count"
        for metric in _USAGE_METRICS
    )
    row = connection.execute(f"SELECT {select_parts} FROM agent_runs {where}", params).fetchone()
    return {
        metric: {
            "min": row[f"{metric}_min"],
            "max": row[f"{metric}_max"],
            "avg": round(row[f"{metric}_avg"]) if row[f"{metric}_avg"] is not None else None,
            "count": row[f"{metric}_count"],
        }
        for metric in _USAGE_METRICS
    }


@router.get("/api/agent-runs/usage-breakdown")
def api_agent_runs_usage_breakdown() -> dict[str, Any]:
    """All-time min/max/avg per usage metric, overall and broken down by agent_role -
    distinct from usage-summary's day-by-day totals, which only cover the last N days."""
    with connect() as connection:
        overall = _usage_stats(connection)
        roles = [
            row["agent_role"]
            for row in connection.execute("SELECT DISTINCT agent_role FROM agent_runs ORDER BY agent_role")
        ]
        by_agent = {role: _usage_stats(connection, "WHERE agent_role = ?", (role,)) for role in roles}
        return {"overall": overall, "by_agent": by_agent}


@router.get("/api/profile")
def api_get_profile() -> dict[str, Any]:
    return get_user_profile()


@router.put("/api/profile")
def api_update_profile(request: ProfileUpdateRequest) -> dict[str, Any]:
    try:
        return update_user_profile(**request.model_dump())
    except ValueError as error:
        raise _tool_error(error) from error


@router.get("/api/household-members")
def api_list_household_members() -> list[dict[str, Any]]:
    return list_household_members()


@router.post("/api/household-members")
def api_add_household_member(request: HouseholdMemberRequest) -> dict[str, Any]:
    try:
        return add_household_member(**request.model_dump())
    except ValueError as error:
        raise _tool_error(error) from error


@router.put("/api/household-members/{member_id}")
def api_update_household_member(member_id: int, request: HouseholdMemberUpdateRequest) -> dict[str, Any]:
    try:
        return update_household_member(member_id, **request.model_dump())
    except ValueError as error:
        raise _tool_error(error) from error


@router.delete("/api/household-members/{member_id}")
def api_delete_household_member(member_id: int) -> dict[str, Any]:
    try:
        return delete_household_member(member_id)
    except ValueError as error:
        raise _tool_error(error) from error


@router.get("/api/recipes/search")
def api_search_recipes(q: str, top_k: int = 10) -> list[dict[str, Any]]:
    try:
        return search_recipes(q, top_k)
    except ValueError as error:
        raise _tool_error(error) from error


@router.get("/api/recipes")
def api_list_recipes(limit: int | None = None, offset: int = 0) -> list[dict[str, Any]]:
    return list_recipes(limit, offset)


@router.get("/api/recipes/{recipe_id}")
def api_get_recipe(recipe_id: int) -> dict[str, Any]:
    try:
        return get_recipe(recipe_id)
    except ValueError as error:
        raise _tool_error(error) from error


@router.post("/api/recipes")
def api_add_recipe(request: RecipeRequest) -> dict[str, Any]:
    try:
        return add_recipe(request.recipe)
    except ValueError as error:
        raise _tool_error(error) from error


@router.put("/api/recipes/{recipe_id}")
def api_update_recipe(recipe_id: int, request: RecipeRequest) -> dict[str, Any]:
    try:
        return update_recipe(recipe_id, request.recipe)
    except ValueError as error:
        raise _tool_error(error) from error


@router.delete("/api/recipes/{recipe_id}")
def api_delete_recipe(recipe_id: int) -> dict[str, Any]:
    try:
        return delete_recipe(recipe_id)
    except ValueError as error:
        raise _tool_error(error) from error


@router.patch("/api/recipes/{recipe_id}/rating")
def api_rate_recipe(recipe_id: int, request: RecipeRatingRequest) -> dict[str, Any]:
    try:
        return rate_recipe(recipe_id, request.rating)
    except ValueError as error:
        raise _tool_error(error) from error


@router.get("/api/chat-sessions")
def api_list_chat_sessions(limit: int = 5) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT session_id, messages_json, updated_at FROM chat_sessions ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    sessions = []
    for row in rows:
        messages = json.loads(row["messages_json"])
        preview = next(
            (message.get("data", {}).get("content", "") for message in messages if message.get("type") == "human"),
            "",
        )
        sessions.append({"session_id": row["session_id"], "updated_at": row["updated_at"], "preview": preview[:120]})
    return sessions


@router.get("/api/chat-sessions/{session_id}")
def api_get_chat_session(session_id: str) -> dict[str, Any]:
    with connect() as connection:
        row = connection.execute("SELECT messages_json FROM chat_sessions WHERE session_id = ?", (session_id,)).fetchone()
    return {"messages": json.loads(row["messages_json"]) if row else []}


@router.put("/api/chat-sessions/{session_id}")
def api_put_chat_session(session_id: str, request: ChatSessionRequest) -> dict[str, Any]:
    with connect() as connection:
        connection.execute(
            "INSERT INTO chat_sessions (session_id, messages_json, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(session_id) DO UPDATE SET messages_json = excluded.messages_json, updated_at = CURRENT_TIMESTAMP",
            (session_id, json.dumps(request.messages)),
        )
    return {"session_id": session_id, "messages": request.messages}
