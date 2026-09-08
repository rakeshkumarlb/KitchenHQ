"""Shared day / meal-type vocabulary and ordering for KitchenHQ.

CANONICAL SOURCE: ``shared/constants.py``. The copies at ``dbmcp/constants.py`` and
``agents/app/constants.py`` are vendored verbatim by ``shared/sync.py`` - the three
services build from separate Docker contexts and share no Python package, so each
needs its own in-process copy. Edit this file, then run ``python shared/sync.py``;
``python shared/sync.py --check`` fails if a copy has drifted.

Non-Python clients (the chatui React app) get these values at runtime instead: dbmcp
includes a ``constants`` block in ``GET /api/dashboard``.
"""

from __future__ import annotations

# Ordered canonical vocabulary. Order is significant: it defines the sort order used
# everywhere a weekly menu or schedule is displayed.
DAYS: tuple[str, ...] = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
MEAL_TYPES: tuple[str, ...] = ("breakfast", "lunch", "snack", "dinner")

# Membership checks (case-sensitive against the lowercase canonical forms).
DAY_SET: frozenset[str] = frozenset(DAYS)
MEAL_TYPE_SET: frozenset[str] = frozenset(MEAL_TYPES)

# 1-based rank for each value, for building explicit ORDER BY / sort-key expressions.
DAY_ORDER: dict[str, int] = {day: rank for rank, day in enumerate(DAYS, start=1)}
MEAL_TYPE_ORDER: dict[str, int] = {meal: rank for rank, meal in enumerate(MEAL_TYPES, start=1)}


def _case_sql(column: str, order: dict[str, int]) -> str:
    whens = " ".join(f"WHEN '{value}' THEN {rank}" for value, rank in order.items())
    return f"CASE {column} {whens} ELSE {len(order) + 1} END"


def day_case_sql(column: str = "day_of_week") -> str:
    """A SQL ``CASE`` expression that sorts *column* monday..sunday (unknown values last)."""
    return _case_sql(column, DAY_ORDER)


def meal_case_sql(column: str = "meal_type") -> str:
    """A SQL ``CASE`` expression that sorts *column* breakfast..dinner (unknown values last)."""
    return _case_sql(column, MEAL_TYPE_ORDER)
