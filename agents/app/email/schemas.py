"""Validated payload contracts for the three email formats. Pure data, no I/O.

Moved verbatim from dbmcp/init_db.py (the `*EmailRequest` models) so the agent-side
tools validate exactly what the MCP tools used to.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

VALID_DAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
VALID_MEAL_TYPES = {"breakfast", "lunch", "snack", "dinner"}


def validate_day(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized not in VALID_DAYS:
        raise ValueError("day_of_week must be a full weekday name")
    return normalized


def validate_meal_type(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized not in VALID_MEAL_TYPES:
        raise ValueError(f"meal_type must be one of {sorted(VALID_MEAL_TYPES)}")
    return normalized


class PrepTaskEmailMeal(BaseModel):
    dish: str = Field(min_length=1)
    meal_type: str = Field(min_length=1)
    servings: int = Field(gt=0)

    @field_validator("meal_type")
    @classmethod
    def _meal_type(cls, value: str) -> str:
        return validate_meal_type(value)


class PrepTaskEmailRequest(BaseModel):
    """Format 1 - Sous Chef prep instructions for a human to execute."""

    prep_date: str = Field(min_length=1, description="The date this prep is for, e.g. 2026-09-01")
    meals: list[PrepTaskEmailMeal] = Field(min_length=1)
    steps: list[str] = Field(min_length=1, description="Ordered, detailed steps to perform")
    ingredients: list[str] = Field(min_length=1, description="Ingredients that will be used")
    notes: str = ""


class WeeklyPlanEmailMeal(BaseModel):
    meal_type: str = Field(min_length=1)
    dish: str = Field(min_length=1)
    macros: str = ""
    # A JSON string array (or legacy free text) - render.parse_lines handles both.
    ingredients: str = ""

    @field_validator("meal_type")
    @classmethod
    def _meal_type(cls, value: str) -> str:
        return validate_meal_type(value)


class WeeklyPlanEmailDay(BaseModel):
    day_of_week: str
    meals: list[WeeklyPlanEmailMeal] = Field(min_length=1)

    @field_validator("day_of_week")
    @classmethod
    def _day(cls, value: str) -> str:
        return validate_day(value)


class WeeklyPlanEmailRequest(BaseModel):
    """Format 2 - Executive Chef weekly menu with reasoning and shopping needs.

    `days` is optional: leave it out and the email is built from the saved weekly_menu
    (fetched over REST), so the agent only passes its reasoning.
    """

    week_start: str = Field(min_length=1)
    week_end: str = Field(min_length=1)
    days: list[WeeklyPlanEmailDay] = Field(default_factory=list)
    considerations: list[str] = Field(min_length=1, description="Why the week looks the way it does")
    shopping_needs: list[str] = Field(default_factory=list, description="Ingredients likely to be bought, in detail")
    notes: str = ""


class ShoppingListEmailItem(BaseModel):
    item_name: str = Field(min_length=1)
    proposed_quantity: float = Field(gt=0)
    unit: str = Field(min_length=1)
    reason: str = ""


class ShoppingListEmailRequest(BaseModel):
    """Format 3 - Pantry Manager shopping suggestions and the reasoning behind them.

    `items` is optional: leave it out and the email is built from the currently pending
    shopping_items (fetched over REST).
    """

    items: list[ShoppingListEmailItem] = Field(default_factory=list)
    reasoning: list[str] = Field(min_length=1)
    notes: str = ""
