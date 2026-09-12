"""The `get_job_context` tool: current date/time + why this run is happening.

Time used to be a static string baked into the system prompt (see `prompts.py`). That
told the model *what* time it was but never *why* a scheduled run had fired - the
`nightly_prep` job is about tomorrow, `morning_cooking` about today, `weekly_menu`
about next week. This module turns both halves into one tool the agent calls on
demand, built fresh per run in `kitchen_agent.run_agent` so it closes over the live
`Settings.tz` and the `job_name` that `jobs.run_job` passes down. Interactive chat has
no job, so `job_name` is None and the tool reports an interactive session.

It also resolves the job's menu scope into concrete weekday names. The `weekly_menu`
table is keyed by weekday ("monday".."sunday"), not by date, and LLMs are unreliable
at "date X falls on which weekday" - so the tool does that arithmetic and hands the
model the exact rows to look at (`job.target_menu_days`).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from langchain_core.tools import StructuredTool

from .config import Settings

# What each scheduled run is about, and which slice of the weekly menu it acts on.
# `menu_scope` is resolved to concrete weekdays in build_job_context. The cron day/time
# is deliberately NOT surfaced - a job can be fired on demand from chatui at any hour,
# so the run must not reason about "is it the normal day for this".
JOB_CONTEXT: dict[str, dict[str, str]] = {
    "weekly_menu": {
        "focus": "the coming Monday-to-Sunday week",
        "rationale": "plan and save next week's full menu before the week starts",
        "menu_scope": "next_week",
    },
    "sunday_prep": {
        "focus": "the whole coming week's cooking",
        "rationale": "a single batch-prep session so weekday cooking is faster",
        "menu_scope": "this_week",
    },
    "nightly_prep": {
        "focus": "tomorrow's breakfast and lunch",
        "rationale": "a small prep task tonight so tomorrow morning's cooking is quick",
        "menu_scope": "tomorrow",
    },
    "morning_cooking": {
        "focus": "today's breakfast and lunch",
        "rationale": "a parallel cooking plan for the meals being made right now",
        "menu_scope": "today",
    },
    "dinner_cooking": {
        "focus": "today's snacks and dinner",
        "rationale": "a parallel cooking plan for tonight's meal",
        "menu_scope": "today",
    },
    "pantry_manager": {
        "focus": "current stock vs. the upcoming week's menu",
        "rationale": "propose a shopping list for whatever is low or needed soon",
        "menu_scope": "this_week",
    },
    "menu_audit": {
        "focus": "every weekly_menu row not yet scored",
        "rationale": "judge the Executive Chef's saved decisions against the household rules and preferences",
    },
    "task_audit": {
        "focus": "every prep-schedule row not yet scored",
        "rationale": "judge the Sous Chef's saved decisions against the household rules and preferences",
    },
}

_MENU_LOOKUP_HINT = (
    "The weekly_menu table is keyed by weekday name (monday..sunday), NOT by date. "
    "Use exactly the weekday(s) in target_menu_days below - do not work out any dates "
    "yourself and do not use today's weekday unless it is listed."
)


def _day(value: date) -> dict[str, str]:
    return {"date": value.isoformat(), "weekday": value.strftime("%A").lower()}


def _target_menu_days(scope: str | None, today: date, monday: date) -> list[dict[str, str]]:
    if scope == "today":
        return [_day(today)]
    if scope == "tomorrow":
        return [_day(today + timedelta(days=1))]
    if scope == "this_week":
        return [_day(monday + timedelta(days=offset)) for offset in range(7)]
    if scope == "next_week":
        return [_day(monday + timedelta(days=7 + offset)) for offset in range(7)]
    return []


def build_job_context(settings: Settings, job_name: str | None = None) -> dict:
    """Current date/time in the household timezone plus this run's intent and target days."""
    now = datetime.now(ZoneInfo(settings.tz))
    today = now.date()
    monday = today - timedelta(days=today.weekday())
    context: dict = {
        "now": {
            "weekday": now.strftime("%A").lower(),
            "date": today.isoformat(),
            "time": now.strftime("%H:%M"),
            "timezone": settings.tz,
            "iso": now.isoformat(),
        },
        "reference_dates": {
            "today": _day(today),
            "tomorrow": _day(today + timedelta(days=1)),
            "week_start_monday": _day(monday),
            "week_end_sunday": _day(monday + timedelta(days=6)),
            "next_week_start_monday": _day(monday + timedelta(days=7)),
        },
    }
    if job_name and job_name in JOB_CONTEXT:
        entry = JOB_CONTEXT[job_name]
        job = {"name": job_name, "focus": entry["focus"], "rationale": entry["rationale"]}
        target_days = _target_menu_days(entry.get("menu_scope"), today, monday)
        if target_days:
            job["menu_lookup_hint"] = _MENU_LOOKUP_HINT
            job["target_menu_days"] = target_days
        context["run_type"] = "scheduled_job"
        context["job"] = job
    else:
        context["run_type"] = "interactive_chat"
        context["job"] = None
    return context


def make_job_context_tool(settings: Settings, job_name: str | None = None) -> StructuredTool:
    """A no-argument `get_job_context` tool bound to this run's settings and job."""

    def _get_job_context() -> str:
        return json.dumps(build_job_context(settings, job_name))

    return StructuredTool.from_function(
        func=_get_job_context,
        name="get_job_context",
        description=(
            "Return the current date and time in the household's timezone, key reference "
            "dates (each with its weekday name), and - when this run is a scheduled job - "
            "what that job is for, why it is running now, and the exact weekly_menu "
            "weekday(s) it should act on (job.target_menu_days). Call this FIRST before any "
            "reasoning about 'today', 'tonight', 'tomorrow', or 'this week', and use "
            "job.target_menu_days verbatim instead of computing dates. Takes no arguments."
        ),
    )
