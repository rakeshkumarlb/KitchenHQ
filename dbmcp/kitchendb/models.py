"""Pydantic request models for the REST surface.

Thin validation wrappers - each route unpacks one of these and calls the matching data
operation in kitchendb/tools/.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from .validation import validate_day


class InventoryAddRequest(BaseModel):
    item_name: str = Field(min_length=1)
    quantity: float = Field(ge=0)
    unit: str = Field(min_length=1)
    category: str = "Pantry"
    minimum_threshold: float = Field(default=0, ge=0)


class InventoryAdjustmentRequest(BaseModel):
    quantity_change: float


class InventoryDiscardRequest(BaseModel):
    quantity: float = Field(gt=0)
    reason: str = "Discarded"


class MenuItemRequest(BaseModel):
    day_of_week: str
    meal_type: str = Field(min_length=1)
    dish_name: str = Field(min_length=1)
    is_kid_friendly: bool
    macros: str
    ingredients: list[str] = Field(min_length=1)
    full_recipe: list[str] = Field(default_factory=list)

    @field_validator("day_of_week")
    @classmethod
    def _validate_day(cls, value: str) -> str:
        return validate_day(value)


class PrepScheduleRequest(BaseModel):
    trigger_day: str
    trigger_time: str = Field(min_length=1)
    task_type: str = Field(min_length=1)
    detailed_instructions: list[str] = Field(min_length=1)
    ingredients_used: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("trigger_day")
    @classmethod
    def _validate_day(cls, value: str) -> str:
        return validate_day(value)


class PrepCompletionRequest(BaseModel):
    is_completed: bool
    human_notes: str = ""


class PrepCancellationRequest(BaseModel):
    human_notes: str = ""


class ShoppingItemRequest(BaseModel):
    item_name: str = Field(min_length=1)
    proposed_quantity: float = Field(gt=0)
    unit: str = Field(min_length=1)


class ShoppingItemsRequest(BaseModel):
    items: list[ShoppingItemRequest] = Field(min_length=1)


class ShoppingItemEditRequest(BaseModel):
    proposed_quantity: float | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, min_length=1)


class ShoppingAcknowledgementRequest(BaseModel):
    acknowledgement_key: str = Field(min_length=1, max_length=200)
    purchased_items: list[dict[str, Any]] = Field(min_length=1)


class AgentRunRequest(BaseModel):
    agent_role: str = Field(min_length=1, max_length=80)
    job_name: str = Field(min_length=1, max_length=80)
    status: str = Field(pattern="^(completed|failed)$")
    result: str = ""
    error: str = ""


class ChatSessionRequest(BaseModel):
    messages: list[dict[str, Any]]


class ProfileUpdateRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    cc_emails: str | None = None
    notes: str | None = None
    notify_on_task_creation: bool | None = None


class HouseholdMemberRequest(BaseModel):
    name: str = Field(min_length=1)
    dietary_preferences: list[str] = Field(default_factory=list)
    health_conditions: list[str] = Field(default_factory=list)


class HouseholdMemberUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    dietary_preferences: list[str] | None = None
    health_conditions: list[str] | None = None
