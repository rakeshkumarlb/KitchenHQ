from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TEST_API_KEY = "test-key"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("KITCHEN_DB_PATH", str(tmp_path / "kitchen.db"))
    monkeypatch.setenv("KITCHENHQ_API_KEY", TEST_API_KEY)
    import init_db

    importlib.reload(init_db)  # re-resolve DATABASE_PATH against this test's tmp_path
    from fastapi.testclient import TestClient

    with TestClient(init_db.app) as test_client:
        test_client.headers.update({"X-API-Key": TEST_API_KEY})
        yield test_client


def test_health_requires_no_auth(client):
    client.headers.pop("X-API-Key")
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_missing_api_key_is_rejected(client):
    client.headers.pop("X-API-Key")
    response = client.get("/api/dashboard")
    assert response.status_code == 401


def test_wrong_api_key_is_rejected(client):
    client.headers["X-API-Key"] = "not-the-key"
    response = client.get("/api/dashboard")
    assert response.status_code == 401


def test_inventory_add_adjust_discard(client):
    added = client.post("/api/inventory", json={"item_name": "Test Flour", "quantity": 10, "unit": "kg"}).json()
    assert added["quantity"] == 10

    adjusted = client.patch(f"/api/inventory/{added['id']}", json={"quantity_change": 5}).json()
    assert adjusted["quantity"] == 15

    discarded = client.post(f"/api/inventory/{added['id']}/discard", json={"quantity": 3, "reason": "spoiled"}).json()
    assert discarded["quantity"] == 12


def test_menu_item_add_and_policy_rejects_restricted_lunch(client):
    saved = client.post(
        "/api/weekly-menu",
        json={
            "day_of_week": "monday",
            "meal_type": "Dinner",
            "dish_name": "Roast chicken",
            "is_kid_friendly": True,
            "macros": "30g protein",
            "ingredients": "chicken, herbs",
        },
    ).json()
    assert saved["dish_name"] == "Roast chicken"

    policy = client.post(
        "/api/weekly-menu/validate",
        json={
            "menu_items": [
                {
                    "day_of_week": "monday",
                    "meal_type": "Lunch",
                    "dish_name": "Chicken rice bowl",
                    "ingredients": "chicken, rice",
                }
            ]
        },
    ).json()
    assert policy["valid"] is False
    assert "chicken" in policy["violations"][0].lower()


def test_prep_schedule_acknowledge_is_idempotent(client):
    inventory = client.post("/api/inventory", json={"item_name": "Test Rice", "quantity": 10, "unit": "kg"}).json()
    task = client.post(
        "/api/prep-schedule",
        json={"trigger_day": "monday", "trigger_time": "08:00", "task_type": "Batch prep", "detailed_instructions": "Cook rice"},
    ).json()

    body = {
        "acknowledgement_key": "prep-key-1",
        "consumed_items": [{"inventory_id": inventory["id"], "quantity": 2, "unit": "kg"}],
    }
    first = client.post(f"/api/prep-schedule/{task['id']}/acknowledge", json=body).json()
    assert first["replayed"] is False

    dashboard = client.get("/api/dashboard").json()
    updated_inventory = next(item for item in dashboard["inventory"] if item["id"] == inventory["id"])
    assert updated_inventory["quantity"] == 8

    second = client.post(f"/api/prep-schedule/{task['id']}/acknowledge", json=body).json()
    assert second["replayed"] is True

    dashboard_after_replay = client.get("/api/dashboard").json()
    unchanged_inventory = next(item for item in dashboard_after_replay["inventory"] if item["id"] == inventory["id"])
    assert unchanged_inventory["quantity"] == 8


def test_shopping_list_acknowledge_is_idempotent(client):
    created = client.post("/api/shopping-lists", json={"items": [{"item_name": "Olive Oil", "proposed_quantity": 2, "unit": "bottle"}]}).json()
    list_id = created["list"]["id"]
    item_id = created["items"][0]["id"]

    body = {"acknowledgement_key": "buy-key-1", "purchased_items": [{"shopping_item_id": item_id, "actual_quantity": 2}]}
    first = client.post(f"/api/shopping-lists/{list_id}/acknowledge", json=body).json()
    assert first["replayed"] is False

    dashboard = client.get("/api/dashboard").json()
    olive_oil = next(item for item in dashboard["inventory"] if item["item_name"] == "Olive Oil")
    assert olive_oil["quantity"] == 2

    second = client.post(f"/api/shopping-lists/{list_id}/acknowledge", json=body).json()
    assert second["replayed"] is True

    dashboard_after_replay = client.get("/api/dashboard").json()
    olive_oil_after = next(item for item in dashboard_after_replay["inventory"] if item["item_name"] == "Olive Oil")
    assert olive_oil_after["quantity"] == 2


def test_chat_session_roundtrip(client):
    empty = client.get("/api/chat-sessions/unknown-session").json()
    assert empty == {"messages": []}

    messages = [{"type": "human", "data": {"content": "hello chef"}}]
    put_response = client.put("/api/chat-sessions/session-1", json={"messages": messages}).json()
    assert put_response["messages"] == messages

    fetched = client.get("/api/chat-sessions/session-1").json()
    assert fetched["messages"] == messages

    replaced = [{"type": "human", "data": {"content": "second message"}}]
    client.put("/api/chat-sessions/session-1", json={"messages": replaced})
    fetched_again = client.get("/api/chat-sessions/session-1").json()
    assert fetched_again["messages"] == replaced
