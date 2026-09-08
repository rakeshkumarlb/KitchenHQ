"""Detailed prep-schedule data operations (propose / complete / cancel)."""

from __future__ import annotations

import json
from typing import Any

from .registry import tool
from ..db import connect, fetch_record, fetch_record_in
from ..units import convert
from ..validation import clean_line_list, normalize_ingredients_used, validate_day


@tool
def get_prep_schedules() -> list[dict[str, Any]]:
    """Read preparation schedules (cancelled tasks are excluded)."""
    with connect() as connection:
        return [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM detailed_prep_schedule WHERE status <> 'cancelled' ORDER BY is_completed, id"
            )
        ]


@tool
def add_detailed_prep_schedule(
    trigger_day: str,
    trigger_time: str,
    task_type: str,
    detailed_instructions: list[str],
    ingredients_used: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Add a detailed preparation task for a human to execute.

    This is the ONLY place that supplies what the task will consume - there is no
    separate step to add it later, so get_inventory first and fill in ingredients_used
    completely before saving.

    Parameters:
      detailed_instructions: ordered list of short, plain-text instruction steps, e.g.
        ["Dice the onions and tomatoes.", "Heat oil in a wide pan over medium heat.",
         "Add the onions and cook 3 minutes until soft."]
        One step per list entry - do not number them yourself and do not pass a single
        text blob; it must be a JSON array of strings (same convention as weekly_menu's
        full_recipe).
      ingredients_used: every ingredient this task will consume, as a JSON array of
        {item_name, quantity, unit} objects, e.g.
        [{"item_name": "Baby spinach", "quantity": 1, "unit": "pcs"},
         {"item_name": "Greek yogurt", "quantity": 200, "unit": "g"}]
        item_name must match (case-insensitively) an item_name already in inventory -
        copy the exact spelling from get_inventory. The moment a human checks this task
        complete, capture_prep_completion_status looks up each item_name here against
        current inventory and deducts quantity from it automatically, recording an
        inventory_transactions row; an item_name with no matching inventory row is
        skipped rather than failing. Leaving this empty (or omitting an ingredient the
        task genuinely uses) means checking the task off will never touch that stock.
        unit: use grams/kilograms (g, kg), millilitres/litres (ml, l) or pieces
        (pcs). Recipe units - tsp, tbsp, cup - are accepted and approximated to
        g/ml on deduction (1 tsp=5, 1 tbsp=15, 1 cup=240). The quantity is
        converted into the inventory row's own unit before it's deducted, so
        "500 g" against a row tracked in kg deducts 0.5. A unit that can't be
        reconciled with the row's unit (e.g. "2 bags" against a kg row) is
        reported back and left un-deducted rather than applied wrongly - so pick
        a unit in the same dimension (mass/volume/count) as the inventory row.
    """
    instructions = clean_line_list(detailed_instructions, field="detailed_instructions", required=True)
    ingredients = normalize_ingredients_used(ingredients_used)
    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO detailed_prep_schedule (trigger_day, trigger_time, task_type, detailed_instructions, ingredients_used) VALUES (?, ?, ?, ?, ?)",
            (validate_day(trigger_day), trigger_time.strip(), task_type.strip(), json.dumps(instructions), json.dumps(ingredients)),
        )
    return fetch_record("detailed_prep_schedule", cursor.lastrowid)


@tool
def capture_prep_completion_status(prep_schedule_id: int, is_completed: bool, human_notes: str = "") -> dict[str, Any]:
    """Capture whether a human completed a detailed preparation task.

    Checking a task complete (is_completed=True) looks up every {item_name, quantity,
    unit} entry the task was saved with (see add_detailed_prep_schedule) against current
    inventory by item_name (case-insensitive) and deducts quantity from each match
    exactly once, recording an inventory_transactions row - safe to call again with
    is_completed=True on an already-acknowledged task (idempotent no-op, returns the
    task unchanged). An item_name with no matching inventory row is skipped rather than
    failing the whole task. Deductions are never blocked by low stock - a match is
    deducted even if it pushes inventory negative, so the shortfall stays visible until
    a shopping run tops it back up. A task saved with no ingredients_used is just marked
    done and can still be unchecked; once a task WITH ingredients has been deducted it
    is finalized ('acknowledged') and cannot be reopened - a later is_completed=False
    call is rejected.
    """
    with connect() as connection:
        task = connection.execute("SELECT * FROM detailed_prep_schedule WHERE id = ?", (prep_schedule_id,)).fetchone()
        if task is None:
            raise ValueError(f"No detailed_prep_schedule record found for id {prep_schedule_id}")
        if task["status"] == "cancelled":
            raise ValueError("prep schedule is cancelled")
        if task["status"] == "acknowledged":
            if is_completed:
                return dict(task)  # already finalized - idempotent no-op
            raise ValueError("prep schedule ingredients were already deducted and cannot be reopened")

        if not is_completed:
            connection.execute(
                "UPDATE detailed_prep_schedule SET is_completed = 0, status = 'proposed', human_notes = ? WHERE id = ?",
                (human_notes, prep_schedule_id),
            )
            return fetch_record_in(connection, "detailed_prep_schedule", prep_schedule_id)

        ingredients = json.loads(task["ingredients_used"] or "[]")

        if not ingredients:
            # Nothing to deduct - mark done without the "ingredients already deducted"
            # lock, so a plain task (e.g. "Wipe counters") can still be unchecked.
            connection.execute(
                "UPDATE detailed_prep_schedule SET is_completed = 1, status = 'completed', human_notes = ? WHERE id = ?",
                (human_notes, prep_schedule_id),
            )
            return fetch_record_in(connection, "detailed_prep_schedule", prep_schedule_id)

        acknowledgement_key = f"prep-{prep_schedule_id}-complete"

        # Prep deductions are never blocked by low stock: the household cooked with what
        # it physically had, even if our tracked number lagged. Present items are
        # deducted and allowed to go negative, so the shortfall stays visible until a
        # shopping run tops it back up; an item_name with no matching inventory row is
        # simply skipped rather than failing the acknowledgement.
        # Each entry's quantity is converted into the matched row's stored unit
        # first (units.convert): "500 g" against a "kg" row deducts 0.5. A line
        # whose unit can't be reconciled with the row's (different dimension, or
        # an unrecognized unit) is skipped and reported in conversion_warnings
        # rather than applied as a wrong number.
        conversion_warnings: list[str] = []
        for index, entry in enumerate(ingredients):
            inventory = connection.execute("SELECT * FROM inventory WHERE item_name = ?", (entry["item_name"],)).fetchone()
            if inventory is None:
                continue
            amount, note, ok = convert(entry["quantity"], entry.get("unit"), inventory["unit"])
            if not ok or amount <= 0:
                conversion_warnings.append(
                    f"{entry['item_name']}: {note or 'quantity resolves to zero'}; not deducted"
                )
                continue
            before = inventory["quantity"]
            after = round(before - amount, 4)
            reason = "Prep acknowledged" + (f" ({note})" if note else "")
            connection.execute(
                "UPDATE inventory SET quantity = ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?",
                (after, inventory["id"]),
            )
            connection.execute(
                "INSERT INTO inventory_transactions (inventory_id, quantity_change, quantity_before, quantity_after, reason, source_type, source_id, idempotency_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (inventory["id"], -amount, before, after, reason, "prep_schedule", prep_schedule_id, f"{acknowledgement_key}:{index}"),
            )
        connection.execute(
            "UPDATE detailed_prep_schedule SET is_completed = 1, status = 'acknowledged', acknowledgement_key = ?, human_notes = ? WHERE id = ?",
            (acknowledgement_key, human_notes, prep_schedule_id),
        )
        result = fetch_record_in(connection, "detailed_prep_schedule", prep_schedule_id)
        if conversion_warnings:
            result["conversion_warnings"] = conversion_warnings
        return result


def cancel_prep_schedule(prep_schedule_id: int, human_notes: str = "") -> dict[str, Any]:
    """Soft-cancel a prep task: it drops out of every schedule/dashboard view but the
    row (and any history) is kept. A task whose ingredients were already deducted
    cannot be cancelled."""
    with connect() as connection:
        task = connection.execute("SELECT * FROM detailed_prep_schedule WHERE id = ?", (prep_schedule_id,)).fetchone()
        if task is None:
            raise ValueError(f"No detailed_prep_schedule record found for id {prep_schedule_id}")
        if task["status"] == "acknowledged":
            raise ValueError("cannot cancel a task whose ingredients were already deducted")
        connection.execute(
            "UPDATE detailed_prep_schedule SET status = 'cancelled', is_completed = 0, human_notes = ? WHERE id = ?",
            (human_notes or task["human_notes"], prep_schedule_id),
        )
    return fetch_record("detailed_prep_schedule", prep_schedule_id)
