"""Shopping-list data operations.

There is no separate "shopping list" entity - this one table IS the pending list.
add/edit/delete/clear are MCP tools; acknowledge_shopping_items is REST-only (a human
records an actual purchase), so it carries no decorator.
"""

from __future__ import annotations

from typing import Any

from .registry import tool
from ..db import connect, fetch_record


@tool
def get_shopping_items() -> list[dict[str, Any]]:
    """Read the pending shopping list - one row per item still needing to be bought.

    There is only ever one shopping list: every row here is currently pending. An item
    disappears from this list the moment it's acknowledged as purchased (see
    acknowledge_shopping_items) - nothing here ever carries a "purchased" status."""
    with connect() as connection:
        return [dict(row) for row in connection.execute("SELECT * FROM shopping_items ORDER BY item_name")]


@tool
def add_shopping_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add ingredients to the one pending shopping list, merging into whatever is
    already there - never touches inventory.

    This is an upsert keyed on item_name (case-insensitive): call it any time something
    is newly needed, whether or not a list already exists. If an item with the same name
    is already pending, its proposed_quantity is increased by the amount given here (and
    its unit is overwritten to whatever this call passes) instead of creating a second
    row - there is no separate "create" vs "append" choice to make, and no need to call
    get_shopping_items first just to decide that. Never propose an item_name that's
    already pending unless you actually want to add more of it.

    Each entry is {item_name, proposed_quantity, unit}. Returns the current state of
    every item this call touched. See acknowledge_shopping_items to record an actual
    purchase and move quantities into inventory.
    """
    if not items:
        raise ValueError("items must contain at least one item")
    with connect() as connection:
        touched_names = []
        for item in items:
            try:
                name, quantity, unit = str(item["item_name"]).strip(), float(item["proposed_quantity"]), str(item["unit"]).strip()
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("each shopping item requires item_name, proposed_quantity, and unit") from error
            if not name or quantity <= 0 or not unit:
                raise ValueError("shopping item names, quantities, and units must be valid")
            connection.execute(
                """
                INSERT INTO shopping_items (item_name, proposed_quantity, unit) VALUES (?, ?, ?)
                ON CONFLICT(item_name) DO UPDATE SET
                    proposed_quantity = proposed_quantity + excluded.proposed_quantity,
                    unit = excluded.unit,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (name, quantity, unit),
            )
            touched_names.append(name)
        placeholders = ",".join("?" * len(touched_names))
        return [
            dict(row)
            for row in connection.execute(
                f"SELECT * FROM shopping_items WHERE item_name IN ({placeholders}) ORDER BY item_name",
                touched_names,
            )
        ]


@tool
def edit_shopping_item(shopping_item_id: int, proposed_quantity: float | None = None, unit: str | None = None) -> dict[str, Any]:
    """Correct a pending shopping item's quantity and/or unit in place. Pass whichever of
    proposed_quantity/unit changed; the other is left as-is."""
    if proposed_quantity is None and unit is None:
        raise ValueError("provide proposed_quantity and/or unit to change")
    if proposed_quantity is not None and proposed_quantity <= 0:
        raise ValueError("proposed_quantity must be greater than zero")
    with connect() as connection:
        row = connection.execute("SELECT * FROM shopping_items WHERE id = ?", (shopping_item_id,)).fetchone()
        if row is None:
            raise ValueError(f"No shopping item found for id {shopping_item_id}")
        connection.execute(
            "UPDATE shopping_items SET proposed_quantity = ?, unit = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (
                proposed_quantity if proposed_quantity is not None else row["proposed_quantity"],
                unit.strip() if unit else row["unit"],
                shopping_item_id,
            ),
        )
    return fetch_record("shopping_items", shopping_item_id)


@tool
def delete_shopping_item(shopping_item_id: int) -> dict[str, Any]:
    """Remove one pending item from the shopping list without buying it (e.g. it's no
    longer needed, or it was a mistaken suggestion). Returns the row as it was."""
    with connect() as connection:
        row = connection.execute("SELECT * FROM shopping_items WHERE id = ?", (shopping_item_id,)).fetchone()
        if row is None:
            raise ValueError(f"No shopping item found for id {shopping_item_id}")
        connection.execute("DELETE FROM shopping_items WHERE id = ?", (shopping_item_id,))
    return dict(row)


@tool
def clear_shopping_items() -> dict[str, Any]:
    """Remove every pending shopping item without buying any of them (start the list
    over from empty). Returns how many rows were cleared."""
    with connect() as connection:
        count = connection.execute("SELECT COUNT(*) FROM shopping_items").fetchone()[0]
        connection.execute("DELETE FROM shopping_items")
    return {"cleared": count}


def acknowledge_shopping_items(acknowledgement_key: str, purchased_items: list[dict[str, Any]]) -> dict[str, Any]:
    """Move purchased quantities into inventory and clear those items off the pending
    shopping list, each exactly once.

    purchased_items is [{shopping_item_id, actual_quantity}]. Inventory is matched (and
    created if it doesn't exist yet) by the shopping item's item_name - never by
    inventory_id, since that's an internal id the caller shouldn't need to track. Once
    applied, the shopping_items row is deleted (this is what "clears" it off the list);
    a replay with the same acknowledgement_key (e.g. a retried request) is a safe no-op
    that will not double-add stock, even though by then the row it originally matched is
    already gone.
    """
    if not acknowledgement_key.strip() or not purchased_items:
        raise ValueError("acknowledgement_key and purchased_items are required")
    normalized_purchases = []
    for item in purchased_items:
        try:
            item_id = int(item["shopping_item_id"])
            quantity = float(item["actual_quantity"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("each purchased item requires shopping_item_id and a numeric actual_quantity") from error
        if quantity < 0:
            raise ValueError("actual quantities cannot be negative")
        normalized_purchases.append((item_id, quantity))

    with connect() as connection:
        applied_ids: list[int] = []
        already_applied_ids: list[int] = []
        for item_id, quantity in normalized_purchases:
            idempotency_key = f"{acknowledgement_key}:{item_id}"
            if connection.execute("SELECT 1 FROM inventory_transactions WHERE idempotency_key = ?", (idempotency_key,)).fetchone():
                already_applied_ids.append(item_id)
                continue
            row = connection.execute("SELECT * FROM shopping_items WHERE id = ?", (item_id,)).fetchone()
            if row is None:
                # Already cleared under a different acknowledgement_key (or never
                # existed) - nothing left here to apply.
                continue
            if quantity > 0:
                inventory = connection.execute("SELECT * FROM inventory WHERE item_name = ?", (row["item_name"],)).fetchone()
                if inventory is None:
                    cursor = connection.execute(
                        "INSERT INTO inventory (item_name, category, quantity, unit) VALUES (?, 'Pantry', ?, ?)",
                        (row["item_name"], quantity, row["unit"]),
                    )
                    inventory_id, before = cursor.lastrowid, 0
                else:
                    inventory_id, before = inventory["id"], inventory["quantity"]
                    connection.execute(
                        "UPDATE inventory SET quantity = quantity + ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?",
                        (quantity, inventory_id),
                    )
                connection.execute(
                    "INSERT INTO inventory_transactions (inventory_id, quantity_change, quantity_before, quantity_after, reason, source_type, source_id, idempotency_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (inventory_id, quantity, before, before + quantity, "Shopping purchase acknowledged", "shopping_item", item_id, idempotency_key),
                )
            connection.execute("DELETE FROM shopping_items WHERE id = ?", (item_id,))
            applied_ids.append(item_id)
        replayed = not applied_ids and bool(already_applied_ids)
        return {"replayed": replayed, "cleared_item_ids": applied_ids}
