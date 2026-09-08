"""Inventory data operations."""

from __future__ import annotations

import sqlite3
from typing import Any

from .registry import tool
from ..db import connect, fetch_record
from ..units import CANONICAL_UNITS, canonicalize_inventory_unit


@tool
def get_inventory() -> list[dict[str, Any]]:
    """Read the current pantry inventory."""
    with connect() as connection:
        return [dict(row) for row in connection.execute("SELECT * FROM inventory ORDER BY category, item_name")]


@tool
def add_inventory(
    item_name: str,
    quantity: float,
    unit: str,
    category: str = "Pantry",
    minimum_threshold: float = 0,
) -> dict[str, Any]:
    """Add a new ingredient to inventory.

    `unit` is the row's canonical stock unit and must be one of g, kg, ml, l, pcs
    (common aliases like "grams"/"litre"/"pieces" are accepted and stored in the
    canonical short form). Every later deduction/intake converts its own quantity
    into this unit, so pick the one you want the running balance reported in.
    """
    if not item_name.strip() or not unit.strip():
        raise ValueError("item_name and unit are required")
    if quantity < 0 or minimum_threshold < 0:
        raise ValueError("quantity and minimum_threshold cannot be negative")
    canonical_unit = canonicalize_inventory_unit(unit)
    if canonical_unit is None:
        raise ValueError(f"unit must be one of {', '.join(CANONICAL_UNITS)} (or a recognized alias); got '{unit.strip()}'")
    with connect() as connection:
        try:
            cursor = connection.execute(
                "INSERT INTO inventory (item_name, category, quantity, unit, minimum_threshold) VALUES (?, ?, ?, ?, ?)",
                (item_name.strip(), category.strip(), quantity, canonical_unit, minimum_threshold),
            )
        except sqlite3.IntegrityError as error:
            raise ValueError(f"Inventory item already exists: {item_name}") from error
    return fetch_record("inventory", cursor.lastrowid)


@tool
def adjust_inventory_quantity(item_id: int, quantity_change: float) -> dict[str, Any]:
    """Increase or decrease an existing ingredient's quantity."""
    if quantity_change == 0:
        raise ValueError("quantity_change cannot be zero")
    with connect() as connection:
        item = connection.execute("SELECT quantity FROM inventory WHERE id = ?", (item_id,)).fetchone()
        if item is None:
            raise ValueError(f"No inventory record found for id {item_id}")
        new_quantity = item["quantity"] + quantity_change
        if new_quantity < 0:
            raise ValueError("quantity cannot become negative")
        connection.execute(
            "UPDATE inventory SET quantity = ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?",
            (new_quantity, item_id),
        )
    return fetch_record("inventory", item_id)


@tool
def remove_or_discard_inventory(item_id: int, quantity: float, reason: str = "Discarded") -> dict[str, Any]:
    """Remove quantity from inventory and record it as discarded."""
    if quantity <= 0:
        raise ValueError("quantity must be greater than zero")
    with connect() as connection:
        item = connection.execute("SELECT item_name, quantity FROM inventory WHERE id = ?", (item_id,)).fetchone()
        if item is None:
            raise ValueError(f"No inventory record found for id {item_id}")
        if quantity > item["quantity"]:
            raise ValueError("discarded quantity cannot exceed available quantity")
        connection.execute(
            "UPDATE inventory SET quantity = quantity - ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?",
            (quantity, item_id),
        )
        connection.execute(
            "INSERT INTO wastage_log (item_name, quantity_wasted) VALUES (?, ?)",
            (f"{item['item_name']} ({reason.strip() or 'Discarded'})", quantity),
        )
    return fetch_record("inventory", item_id)
