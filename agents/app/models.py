from __future__ import annotations

from pydantic import BaseModel, Field


class SousChefResult(BaseModel):
    summary: str = Field(description="Short description of the prep schedules created")
    prep_schedule_ids: list[int] = Field(default_factory=list)


class PantryManagerResult(BaseModel):
    summary: str = Field(description="Short explanation of the shopping recommendation")
    shopping_item_ids: list[int] = Field(default_factory=list)


class ExecutiveChefResult(BaseModel):
    summary: str = Field(description="Short description of the weekly menu that was saved")
    menu_item_ids: list[int] = Field(default_factory=list)


# Per-role response_format for interactive turns. executive_chef is intentionally
# absent: chat replies stay conversational text. The weekly_menu *job* still gets a
# structured result - jobs.py passes ExecutiveChefResult to run_agent explicitly.
RESPONSE_FORMATS = {
    "sous_chef": SousChefResult,
    "pantry_manager": PantryManagerResult,
}
