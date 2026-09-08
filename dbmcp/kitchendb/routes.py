"""The REST surface: one thin route per data operation, plus /api/health and
/api/dashboard.

Every route either reads directly or unpacks a Pydantic model and calls the matching
function in kitchendb/tools/. A ValueError from a data operation becomes HTTP 400.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException

from constants import DAY_ORDER, DAYS, MEAL_TYPE_ORDER, MEAL_TYPES, day_case_sql, meal_case_sql

from .db import connect, fetch_record_in
from .models import (
    AgentRunRequest,
    ChatSessionRequest,
    InventoryAddRequest,
    InventoryAdjustmentRequest,
    InventoryDiscardRequest,
    MenuItemRequest,
    MenuRatingRequest,
    PrepCancellationRequest,
    PrepCompletionRequest,
    PrepScheduleRequest,
    ProfileUpdateRequest,
    ShoppingAcknowledgementRequest,
    ShoppingItemEditRequest,
    ShoppingItemsRequest,
)
from .tools.inventory import add_inventory, adjust_inventory_quantity, remove_or_discard_inventory
from .tools.prep import add_detailed_prep_schedule, cancel_prep_schedule, capture_prep_completion_status
from .tools.profile import get_user_profile, update_user_profile
from .tools.shopping import (
    acknowledge_shopping_items,
    add_shopping_items,
    clear_shopping_items,
    delete_shopping_item,
    edit_shopping_item,
    get_shopping_items,
)
from .tools.weekly_menu import add_weekly_menu_item, capture_weekly_menu_rating

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
            "profile": (lambda row: dict(row) if row is not None else {})(
                connection.execute("SELECT * FROM user_profile WHERE id = 1").fetchone()
            ),
            # Day / meal vocabulary for non-Python clients (the chatui React app) - the
            # single source of truth is shared/constants.py, vendored here as constants.py.
            "constants": {
                "days": list(DAYS),
                "meal_types": list(MEAL_TYPES),
                "day_order": DAY_ORDER,
                "meal_type_order": MEAL_TYPE_ORDER,
            },
        }


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


@router.post("/api/weekly-menu/{menu_item_id}/rating")
def api_capture_rating(menu_item_id: int, request: MenuRatingRequest) -> dict[str, Any]:
    try:
        return capture_weekly_menu_rating(menu_item_id, **request.model_dump())
    except ValueError as error:
        raise _tool_error(error) from error


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
            "INSERT INTO agent_runs (agent_role, job_name, status, result, error) VALUES (?, ?, ?, ?, ?)",
            (request.agent_role, request.job_name, request.status, request.result, request.error),
        )
        return fetch_record_in(connection, "agent_runs", cursor.lastrowid)


@router.get("/api/agent-runs")
def api_agent_runs() -> list[dict[str, Any]]:
    with connect() as connection:
        return [dict(row) for row in connection.execute("SELECT * FROM agent_runs ORDER BY id DESC LIMIT 100")]


@router.get("/api/profile")
def api_get_profile() -> dict[str, Any]:
    return get_user_profile()


@router.put("/api/profile")
def api_update_profile(request: ProfileUpdateRequest) -> dict[str, Any]:
    try:
        return update_user_profile(**request.model_dump())
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
