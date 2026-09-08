"""Validated payload contracts for the three email formats. Pure data, no I/O.

Moved verbatim from dbmcp/init_db.py (the `*EmailRequest` models) so the agent-side
tools validate exactly what the MCP tools used to.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from ..constants import DAY_SET as VALID_DAYS, MEAL_TYPE_SET as VALID_MEAL_TYPES


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

    `days` is optional and normally omitted: the email is then built from the saved
    weekly_menu (fetched over REST). This is the one email that still reads the DB -
    it summarizes a whole week, and sending it is not an enforced job step, so it must
    not depend on the model re-emitting all 28 slots faithfully.
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

    `items` is required: the agent passes the shopping items it just added (or read
    back with get_shopping_items). The tool only renders and sends - it does not read
    the DB for this email.
    """

    items: list[ShoppingListEmailItem] = Field(min_length=1)
    reasoning: list[str] = Field(min_length=1)
    notes: str = ""
