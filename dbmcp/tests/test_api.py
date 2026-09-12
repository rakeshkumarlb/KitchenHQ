from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TEST_API_KEY = "test-key"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("KITCHEN_DB_PATH", str(tmp_path / "kitchen.db"))
    monkeypatch.setenv("KITCHENHQ_API_KEY", TEST_API_KEY)

    from fastapi.testclient import TestClient
    from kitchendb import create_app

    # A fresh app (and MCP session manager) per test; connect() reads KITCHEN_DB_PATH
    # dynamically, so each case gets its own temp database.
    with TestClient(create_app()) as test_client:
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
    import init_db

    saved = client.post(
        "/api/weekly-menu",
        json={
            "day_of_week": "monday",
            "meal_type": "Dinner",
            "dish_name": "Roast chicken",
            "is_kid_friendly": True,
            "macros": "30g protein",
            "ingredients": ["chicken thigh", "herbs"],
            "full_recipe": ["Season the chicken", "Roast for 40 minutes"],
        },
    ).json()
    assert saved["dish_name"] == "Roast chicken"
    assert json.loads(saved["ingredients"]) == ["chicken thigh", "herbs"]
    assert saved["updated_at"]

    # POST /api/weekly-menu/validate is soft-deleted; the policy function is still the
    # MCP tool, so exercise it directly.
    policy = init_db.validate_weekly_menu_policy(
        [
            {
                "day_of_week": "monday",
                "meal_type": "lunch",
                "dish_name": "Chicken rice bowl",
                "ingredients": "chicken, rice",
            }
        ]
    )
    assert policy["valid"] is False
    assert "chicken" in policy["violations"][0].lower()


def test_shopping_items_acknowledge_is_idempotent(client):
    created = client.post("/api/shopping-items", json={"items": [{"item_name": "Olive Oil", "proposed_quantity": 2, "unit": "bottle"}]}).json()
    item_id = created[0]["id"]

    body = {"acknowledgement_key": "buy-key-1", "purchased_items": [{"shopping_item_id": item_id, "actual_quantity": 2}]}
    first = client.post("/api/shopping-items/acknowledge", json=body).json()
    assert first["replayed"] is False

    dashboard = client.get("/api/dashboard").json()
    olive_oil = next(item for item in dashboard["inventory"] if item["item_name"] == "Olive Oil")
    assert olive_oil["quantity"] == 2
    assert dashboard["shopping_items"] == []

    second = client.post("/api/shopping-items/acknowledge", json=body).json()
    assert second["replayed"] is True

    dashboard_after_replay = client.get("/api/dashboard").json()
    olive_oil_after = next(item for item in dashboard_after_replay["inventory"] if item["item_name"] == "Olive Oil")
    assert olive_oil_after["quantity"] == 2


def test_add_shopping_items_is_an_upsert_that_merges_quantity(client):
    client.post("/api/shopping-items", json={"items": [{"item_name": "Milk", "proposed_quantity": 1, "unit": "l"}]})
    merged = client.post("/api/shopping-items", json={"items": [{"item_name": "milk", "proposed_quantity": 2, "unit": "l"}, {"item_name": "Butter", "proposed_quantity": 200, "unit": "g"}]}).json()

    items = client.get("/api/shopping-items").json()
    assert {item["item_name"]: item["proposed_quantity"] for item in items} == {"Milk": 3, "Butter": 200}
    assert len(items) == 2

    milk = next(item for item in merged if item["item_name"].lower() == "milk")
    body = {"acknowledgement_key": "buy-milk-1", "purchased_items": [{"shopping_item_id": milk["id"], "actual_quantity": 3}]}
    client.post("/api/shopping-items/acknowledge", json=body)

    remaining = client.get("/api/shopping-items").json()
    assert {item["item_name"] for item in remaining} == {"Butter"}


def test_shopping_item_edit_and_delete(client):
    added = client.post("/api/shopping-items", json={"items": [{"item_name": "Flour", "proposed_quantity": 1, "unit": "kg"}]}).json()[0]

    edited = client.patch(f"/api/shopping-items/{added['id']}", json={"proposed_quantity": 2}).json()
    assert edited["proposed_quantity"] == 2
    assert edited["unit"] == "kg"

    client.delete(f"/api/shopping-items/{added['id']}")
    assert client.get("/api/shopping-items").json() == []


def test_dashboard_reports_recent_consumption(client):
    inventory = client.post("/api/inventory", json={"item_name": "Test Oats", "quantity": 1000, "unit": "g"}).json()
    task = client.post(
        "/api/prep-schedule",
        json={
            "trigger_day": "monday",
            "trigger_time": "08:00",
            "task_type": "Batch prep",
            "detailed_instructions": ["Cook oats"],
            "ingredients_used": [{"item_name": "Test Oats", "quantity": 250, "unit": "g"}],
        },
    ).json()
    client.patch(f"/api/prep-schedule/{task['id']}/completion", json={"is_completed": True})

    consumption = client.get("/api/dashboard").json()["consumption"]
    oats = next(row for row in consumption if row["item_name"] == "Test Oats")
    assert oats["quantity_consumed"] == 250
    assert oats["transaction_count"] == 1
    assert inventory["id"]


def test_prep_completion_deducts_consumption_once_and_locks(client):
    inventory = client.post("/api/inventory", json={"item_name": "Test Paneer", "quantity": 500, "unit": "g"}).json()
    task = client.post(
        "/api/prep-schedule",
        json={
            "trigger_day": "monday",
            "trigger_time": "08:00",
            "task_type": "Dinner prep",
            "detailed_instructions": ["Press paneer"],
            "ingredients_used": [{"item_name": "Test Paneer", "quantity": 200, "unit": "g"}],
        },
    ).json()

    completed = client.patch(f"/api/prep-schedule/{task['id']}/completion", json={"is_completed": True}).json()
    assert completed["is_completed"] == 1
    assert completed["status"] == "acknowledged"

    dashboard = client.get("/api/dashboard").json()
    assert next(item for item in dashboard["inventory"] if item["id"] == inventory["id"])["quantity"] == 300

    # Re-checking is an idempotent no-op, not a second deduction.
    again = client.patch(f"/api/prep-schedule/{task['id']}/completion", json={"is_completed": True}).json()
    assert again["status"] == "acknowledged"
    dashboard_after = client.get("/api/dashboard").json()
    assert next(item for item in dashboard_after["inventory"] if item["id"] == inventory["id"])["quantity"] == 300

    # Once deducted the task cannot be reopened.
    reopen = client.patch(f"/api/prep-schedule/{task['id']}/completion", json={"is_completed": False})
    assert reopen.status_code == 400


def test_prep_acknowledge_allows_negative_balance(client):
    inventory = client.post("/api/inventory", json={"item_name": "Basmati rice", "quantity": 1, "unit": "kg"}).json()
    task = client.post(
        "/api/prep-schedule",
        json={
            "trigger_day": "monday",
            "trigger_time": "08:00",
            "task_type": "Batch prep",
            "detailed_instructions": ["Cook rice"],
            "ingredients_used": [{"item_name": "Basmati rice", "quantity": 5, "unit": "kg"}],
        },
    ).json()

    acknowledged = client.patch(f"/api/prep-schedule/{task['id']}/completion", json={"is_completed": True})
    assert acknowledged.status_code == 200
    assert acknowledged.json()["status"] == "acknowledged"

    dashboard = client.get("/api/dashboard").json()
    rice = next(item for item in dashboard["inventory"] if item["id"] == inventory["id"])
    assert rice["quantity"] == -4
    consumed = next(row for row in dashboard["consumption"] if row["inventory_id"] == inventory["id"])
    assert consumed["quantity_consumed"] == 5


def test_prep_ingredient_with_no_matching_inventory_is_skipped_not_failed(client):
    task = client.post(
        "/api/prep-schedule",
        json={
            "trigger_day": "monday",
            "trigger_time": "08:00",
            "task_type": "Batch prep",
            "detailed_instructions": ["Use an ingredient that isn't tracked"],
            "ingredients_used": [{"item_name": "Nonexistent Spice", "quantity": 1, "unit": "tsp"}],
        },
    ).json()
    completed = client.patch(f"/api/prep-schedule/{task['id']}/completion", json={"is_completed": True})
    assert completed.status_code == 200
    assert completed.json()["status"] == "acknowledged"


def test_profile_roundtrip_and_validation(client):
    default_profile = client.get("/api/profile").json()
    assert default_profile["id"] == 1
    assert default_profile["notify_on_task_creation"] == 1

    updated = client.put("/api/profile", json={"name": "Sam Rivera", "email": "sam@example.com", "notify_on_task_creation": False}).json()
    assert updated["name"] == "Sam Rivera"
    assert updated["email"] == "sam@example.com"
    assert updated["notify_on_task_creation"] == 0

    # A partial patch leaves untouched fields alone.
    patched = client.put("/api/profile", json={"cc_emails": "chef@example.com, partner@example.com"}).json()
    assert patched["cc_emails"] == "chef@example.com, partner@example.com"
    assert patched["name"] == "Sam Rivera"

    rejected = client.put("/api/profile", json={"email": "not-an-email"})
    assert rejected.status_code == 400

    assert client.get("/api/dashboard").json()["profile"]["name"] == "Sam Rivera"


def _add_menu_item(client, dish_name, *, day, meal):
    return client.post(
        "/api/weekly-menu",
        json={
            "day_of_week": day,
            "meal_type": meal,
            "dish_name": dish_name,
            "is_kid_friendly": True,
            "macros": "20g protein",
            "ingredients": ["assorted"],
        },
    ).json()


def test_household_members_crud_and_preferences(client):
    added = client.post(
        "/api/household-members",
        json={"name": "Kiran", "dietary_preferences": ["vegetarian", "no nuts"], "health_conditions": ["diabetic"]},
    ).json()
    assert added["name"] == "Kiran"
    assert added["dietary_preferences"] == ["vegetarian", "no nuts"]
    assert added["health_conditions"] == ["diabetic"]

    listed = client.get("/api/household-members").json()
    assert [m["name"] for m in listed] == ["Kiran"]

    updated = client.put(f"/api/household-members/{added['id']}", json={"health_conditions": ["diabetic", "lactose intolerant"]}).json()
    assert updated["health_conditions"] == ["diabetic", "lactose intolerant"]
    assert updated["dietary_preferences"] == ["vegetarian", "no nuts"]  # untouched by the partial patch

    assert client.get("/api/dashboard").json()["household_members"][0]["name"] == "Kiran"

    deleted = client.delete(f"/api/household-members/{added['id']}")
    assert deleted.status_code == 200
    assert client.get("/api/household-members").json() == []

    missing = client.put(f"/api/household-members/{added['id']}", json={"name": "Anyone"})
    assert missing.status_code == 400


def test_weekly_menu_audit_flow(client):
    # get_unaudited_weekly_menu_items / record_weekly_menu_audit are MCP-only tools
    # (no REST route, like validate_weekly_menu_policy above), so exercise them directly.
    from kitchendb.tools.audit import get_unaudited_weekly_menu_items, record_weekly_menu_audit

    saved = _add_menu_item(client, "Dish 0", day="monday", meal="lunch")
    assert saved["score"] is None

    # A fresh DB seeds 28 menu rows, none audited yet, so this one is among them.
    unaudited = get_unaudited_weekly_menu_items()
    assert saved["id"] in [row["id"] for row in unaudited]
    record_weekly_menu_audit(saved["id"], 85, "Balanced and vegetarian, matches the household's lunch rule.")

    menu = client.get("/api/dashboard").json()["menu"]
    audited = next(row for row in menu if row["id"] == saved["id"])
    assert audited["score"] == 85
    assert "vegetarian" in audited["audit_feedback"]

    # Re-saving the slot clears the audit - it's a new decision awaiting judgement.
    resaved = _add_menu_item(client, "Dish 0 v2", day="monday", meal="lunch")
    assert resaved["score"] is None
    assert resaved["audit_feedback"] is None


def test_prep_task_audit_includes_cancelled(client):
    from kitchendb.db import fetch_record
    from kitchendb.tools.audit import get_unaudited_prep_tasks, record_prep_task_audit

    task = client.post(
        "/api/prep-schedule",
        json={"trigger_day": "monday", "trigger_time": "07:00", "task_type": "Prep", "detailed_instructions": ["Chop vegetables."]},
    ).json()
    client.post(f"/api/prep-schedule/{task['id']}/cancel", json={"human_notes": "Not needed"})

    # get_prep_schedules excludes cancelled tasks, but the audit still needs to judge
    # the Sous Chef's original decision, so get_unaudited_prep_tasks includes it.
    unaudited = get_unaudited_prep_tasks()
    assert task["id"] in [row["id"] for row in unaudited]

    record_prep_task_audit(task["id"], 70, "Reasonable ingredient choices for the assigned meal.")
    stored = fetch_record("detailed_prep_schedule", task["id"])
    assert stored["score"] == 70
    assert stored["status"] == "cancelled"


# Email notifications moved out of dbmcp - see agents/app/email/. The
# send/skip/validation behaviour is covered there; dbmcp no longer has SMTP config,
# send_*_email tools, or /api/notifications/* routes.


def test_weekly_menu_item_is_an_upsert_with_no_duplicates(client):
    for dish in ("First take", "Second take", "Third take"):
        client.post(
            "/api/weekly-menu",
            json={"day_of_week": "monday", "meal_type": "breakfast", "dish_name": dish,
                  "is_kid_friendly": True, "macros": "20P", "ingredients": ["x"]},
        )
    menu = client.get("/api/dashboard").json()["menu"]
    monday_breakfast = [row for row in menu if row["day_of_week"] == "monday" and row["meal_type"] == "breakfast"]
    assert len(monday_breakfast) == 1
    assert monday_breakfast[0]["dish_name"] == "Third take"


def test_prep_schedule_creation_returns_row_without_sending_email(client):
    # dbmcp has no email path at all now - creating a prep row just writes the row.
    client.put("/api/profile", json={"email": "sam@example.com"})
    created = client.post(
        "/api/prep-schedule",
        json={"trigger_day": "monday", "trigger_time": "08:00", "task_type": "Batch prep", "detailed_instructions": ["Cook rice"]},
    )
    assert created.status_code == 200
    assert created.json()["status"] == "proposed"
    assert json.loads(created.json()["detailed_instructions"]) == ["Cook rice"]
    assert json.loads(created.json()["ingredients_used"]) == []


def test_prep_completion_without_consumption_just_marks_done(client):
    task = client.post(
        "/api/prep-schedule",
        json={"trigger_day": "tuesday", "trigger_time": "09:00", "task_type": "Tidy", "detailed_instructions": ["Wipe counters"]},
    ).json()
    completed = client.patch(f"/api/prep-schedule/{task['id']}/completion", json={"is_completed": True}).json()
    assert completed["is_completed"] == 1
    assert completed["status"] == "completed"


def test_prep_cancel_hides_task_and_blocks_after_deduction(client):
    task = client.post(
        "/api/prep-schedule",
        json={"trigger_day": "wednesday", "trigger_time": "07:00", "task_type": "Batch prep", "detailed_instructions": ["Soak beans"]},
    ).json()
    cancelled = client.post(f"/api/prep-schedule/{task['id']}/cancel", json={}).json()
    assert cancelled["status"] == "cancelled"

    dashboard = client.get("/api/dashboard").json()
    assert all(row["id"] != task["id"] for row in dashboard["tasks"])

    client.post("/api/inventory", json={"item_name": "Test Beans", "quantity": 5, "unit": "kg"})
    deducting = client.post(
        "/api/prep-schedule",
        json={
            "trigger_day": "wednesday",
            "trigger_time": "07:30",
            "task_type": "Batch prep",
            "detailed_instructions": ["Cook beans"],
            "ingredients_used": [{"item_name": "Test Beans", "quantity": 1, "unit": "kg"}],
        },
    ).json()
    client.patch(f"/api/prep-schedule/{deducting['id']}/completion", json={"is_completed": True})
    blocked = client.post(f"/api/prep-schedule/{deducting['id']}/cancel", json={})
    assert blocked.status_code == 400


def test_dashboard_caps_completed_tasks_at_ten(client):
    for index in range(12):
        task = client.post(
            "/api/prep-schedule",
            json={"trigger_day": "monday", "trigger_time": f"0{index % 9}:00", "task_type": "Tidy", "detailed_instructions": [f"job {index}"]},
        ).json()
        client.patch(f"/api/prep-schedule/{task['id']}/completion", json={"is_completed": True})

    dashboard = client.get("/api/dashboard").json()
    completed = [row for row in dashboard["tasks"] if row["is_completed"]]
    assert len(completed) == 10
    assert {json.loads(row["detailed_instructions"])[0] for row in completed} == {f"job {index}" for index in range(2, 12)}


def test_prep_deduction_converts_into_the_stored_unit(client):
    # Row tracked in kg; task consumes 500 g -> deduct 0.5, not 500.
    inventory = client.post("/api/inventory", json={"item_name": "Biryani rice", "quantity": 2, "unit": "kg"}).json()
    task = client.post(
        "/api/prep-schedule",
        json={
            "trigger_day": "monday",
            "trigger_time": "08:00",
            "task_type": "Batch prep",
            "detailed_instructions": ["Cook rice"],
            "ingredients_used": [{"item_name": "Biryani rice", "quantity": 500, "unit": "g"}],
        },
    ).json()

    completed = client.patch(f"/api/prep-schedule/{task['id']}/completion", json={"is_completed": True}).json()
    assert "conversion_warnings" not in completed

    dashboard = client.get("/api/dashboard").json()
    assert next(item for item in dashboard["inventory"] if item["id"] == inventory["id"])["quantity"] == 1.5


def test_prep_deduction_skips_unconvertible_unit_and_warns(client):
    inventory = client.post("/api/inventory", json={"item_name": "Jasmine rice", "quantity": 3, "unit": "kg"}).json()
    task = client.post(
        "/api/prep-schedule",
        json={
            "trigger_day": "monday",
            "trigger_time": "08:00",
            "task_type": "Batch prep",
            "detailed_instructions": ["Cook rice"],
            "ingredients_used": [{"item_name": "Jasmine rice", "quantity": 2, "unit": "bags"}],
        },
    ).json()

    completed = client.patch(f"/api/prep-schedule/{task['id']}/completion", json={"is_completed": True}).json()
    assert completed["status"] == "acknowledged"
    assert any("Jasmine rice" in warning for warning in completed["conversion_warnings"])

    dashboard = client.get("/api/dashboard").json()
    # Balance untouched - the bad line was skipped, not applied as "-2 kg".
    assert next(item for item in dashboard["inventory"] if item["id"] == inventory["id"])["quantity"] == 3


def test_shopping_acknowledge_converts_into_the_stored_unit(client):
    inventory = client.post("/api/inventory", json={"item_name": "Butter", "quantity": 100, "unit": "g"}).json()
    item = client.post(
        "/api/shopping-items", json={"items": [{"item_name": "Butter", "proposed_quantity": 2, "unit": "kg"}]}
    ).json()[0]

    ack = client.post(
        "/api/shopping-items/acknowledge",
        json={"acknowledgement_key": "run-1", "purchased_items": [{"shopping_item_id": item["id"], "actual_quantity": 2}]},
    ).json()
    assert ack["cleared_item_ids"] == [item["id"]]

    dashboard = client.get("/api/dashboard").json()
    assert next(row for row in dashboard["inventory"] if row["id"] == inventory["id"])["quantity"] == 2100


def test_shopping_acknowledge_leaves_unconvertible_item_on_the_list(client):
    inventory = client.post("/api/inventory", json={"item_name": "Olive oil", "quantity": 500, "unit": "ml"}).json()
    item = client.post(
        "/api/shopping-items", json={"items": [{"item_name": "Olive oil", "proposed_quantity": 1, "unit": "kg"}]}
    ).json()[0]

    ack = client.post(
        "/api/shopping-items/acknowledge",
        json={"acknowledgement_key": "run-1", "purchased_items": [{"shopping_item_id": item["id"], "actual_quantity": 1}]},
    ).json()
    assert ack["cleared_item_ids"] == []
    assert any("Olive oil" in warning for warning in ack["warnings"])

    dashboard = client.get("/api/dashboard").json()
    assert next(row for row in dashboard["inventory"] if row["id"] == inventory["id"])["quantity"] == 500
    assert any(row["id"] == item["id"] for row in dashboard["shopping_items"])  # still pending


def test_add_inventory_rejects_non_canonical_unit_and_normalizes_aliases(client):
    rejected = client.post("/api/inventory", json={"item_name": "Coriander", "quantity": 2, "unit": "bunch"})
    assert rejected.status_code == 400

    normalized = client.post("/api/inventory", json={"item_name": "Flour", "quantity": 1, "unit": "kilograms"}).json()
    assert normalized["unit"] == "kg"


def test_dashboard_includes_day_meal_constants(client):
    constants = client.get("/api/dashboard").json()["constants"]
    assert constants["days"] == ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    assert constants["meal_types"] == ["breakfast", "lunch", "snack", "dinner"]
    assert constants["day_order"]["monday"] == 1
    assert constants["meal_type_order"]["dinner"] == 4


def test_constants_py_matches_shared_canonical_copy():
    vendored = Path(__file__).resolve().parent.parent / "constants.py"
    shared = Path(__file__).resolve().parent.parent.parent / "shared" / "constants.py"
    if not shared.exists():
        pytest.skip("shared/ not present (standalone dbmcp checkout)")
    assert vendored.read_bytes() == shared.read_bytes(), (
        "dbmcp/constants.py has drifted from shared/constants.py — run `python shared/sync.py`"
    )


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
