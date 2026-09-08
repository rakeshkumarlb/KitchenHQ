from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import Settings

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

OPERATING_RULES = """
Operating rules:
- Call get_job_context before any date-relative reasoning ("today", "tonight", "tomorrow", "this week") and to learn why a scheduled run fired — never guess the date.
- Always query the relevant tool before making claims about current stock, menus, or tasks — never rely on memory of a past turn or job for current data.
- Use the write tools when the request says to save, record, update, or log something.
- For scheduled jobs, complete the requested database writes autonomously and report the result; there is no human to ask, so make the best reasonable call and note any assumption in your report.
- For interactive conversations, if a request is genuinely ambiguous, ask one concise clarifying question instead of inventing database facts.
- For interactive conversations, be detailed and conversational: explain your reasoning, summarize relevant data, and give practical next steps. Use headings and bullets when they improve readability.
"""


def _read(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


BASE_SYSTEM_PROMPT = _read("system.md")

ROLE_PROMPTS = {
    "executive_chef": _read("executive_chef.md"),
    "sous_chef": _read("sous_chef.md"),
    "pantry_manager": _read("pantry_manager.md"),
}


def current_context_block(settings: Settings) -> str:
    now = datetime.now(ZoneInfo(settings.tz))
    return (
        f'Current time: {now.strftime("%A %Y-%m-%d %H:%M")} ({settings.tz}). '
        "Call get_job_context for date math (tomorrow, this week's Monday-Sunday) and the "
        "reason this run was triggered; never guess a date, and never trust a date mentioned "
        "earlier in the conversation over get_job_context."
    )


def system_prompt_for(role: str, settings: Settings) -> str:
    return "\n\n".join(
        [
            current_context_block(settings),
            BASE_SYSTEM_PROMPT,
            OPERATING_RULES,
            f"Your role:\n{ROLE_PROMPTS[role]}",
        ]
    )
