"""Runs one agent turn end-to-end: build model + MCP tools, execute, dispose, return.

Replaces the old `KitchenHQAgent` class, which built its model and MCP client once in
`__init__`/`start()` and kept them alive for the process lifetime. Nothing here is
shared across calls, so there is no persistent connection to leak and no need for the
old cross-request lock - concurrent calls for different sessions no longer serialize
each other.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents import create_agent
from pydantic import BaseModel

from .config import Settings
from .email import make_email_tools
from .history import load_history, save_history
from .job_context import make_job_context_tool
from .llm import build_model, dispose_model
from .mcp_tools import load_tools
from .models import RESPONSE_FORMATS
from .prompts import system_prompt_for

logger = logging.getLogger("kitchenhq-agent")

# langgraph super-step budget for one invoke. The default (25) is tight for a job that
# gathers context and then does several writes; a model that (wrongly) saves a menu one
# item at a time would otherwise blow it.
_RECURSION_LIMIT = 60
# How many corrective nudges to send a scheduled job that stopped before doing its
# required writes. Small models often end the turn after the "gather context" tool
# calls, or save only part of a 28-slot week; a few "you're not finished, do X now"
# turns unstick them. Each nudge is a full agent re-invoke, so keep this modest.
_MAX_FOLLOWUPS = 3


async def run_agent(
    role: str,
    text: str,
    settings: Settings,
    *,
    session_id: str = "default",
    remember: bool = True,
    trace: bool = False,
    job_name: str | None = None,
    require_tools: list[str | tuple[str, ...]] | None = None,
    require_tool_counts: dict[str, int] | None = None,
    response_format: type | None = None,
) -> str:
    """Run one agent turn. `trace=True` is a debug aid (see cli.py) that returns a
    human-readable event-by-event transcript instead of the model's actual reply or
    structured_response — never pass it where the result is parsed programmatically
    (e.g. jobs.py's JSON validation), or you'll get a result that can't be parsed.

    `require_tools` names tools a scheduled job must call (e.g. `add_weekly_menu_item`);
    if the run ends without them, up to `_MAX_FOLLOWUPS` corrective turns are sent, then
    a `RuntimeError` is raised. Ignored when `trace=True`. An entry may itself be a tuple
    of alternative tool names when either one satisfies the requirement (no current job
    needs this, but the mechanism stays available for a future one that does).

    `response_format` overrides the per-role default (`RESPONSE_FORMATS[role]`) — jobs.py
    passes one so a job always returns structured JSON even for roles whose chat replies
    stay free text (executive_chef)."""
    model = build_model(settings)
    try:
        tools = await load_tools(settings)
        tools.append(make_job_context_tool(settings, job_name))
        # Email tools are built locally (not from MCP) - they send SMTP mail and
        # back-fill the saved menu / shopping list over dbmcp's REST API. Same
        # per-run lifetime as get_job_context.
        tools.extend(make_email_tools(settings))
        if response_format is None:
            response_format = RESPONSE_FORMATS.get(role)
        agent = create_agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt_for(role, settings),
            **({"response_format": response_format} if response_format else {}),
        )
        logger.info("Running %s agent with %d tools", role, len(tools))

        history = await load_history(session_id, settings) if remember else []
        messages: list[Any] = [*history, {"role": "user", "content": text}]

        if trace:
            result_messages = await _stream_agent(agent, messages)
            structured_response = None
        else:
            result = await agent.ainvoke({"messages": messages}, {"recursion_limit": _RECURSION_LIMIT})
            result_messages = result["messages"]
            structured_response = result.get("structured_response")

            for attempt in range(1, _MAX_FOLLOWUPS + 1):
                shortfalls = _all_shortfalls(job_name, require_tools, require_tool_counts, result_messages)
                if not shortfalls:
                    break
                logger.warning(
                    "Job %s incomplete (%s) after attempt %d/%d; nudging",
                    job_name, "; ".join(shortfalls), attempt, _MAX_FOLLOWUPS,
                )
                nudge = (
                    "You have NOT finished this task. Still outstanding: "
                    + "; ".join(shortfalls)
                    + ". Use the data you already gathered above — do not re-fetch it — "
                    "and if a piece of optional context (favourite recipes, chef note) "
                    "was empty, proceed without it. Do it now, then reply with a short summary."
                )
                result = await agent.ainvoke(
                    {"messages": [*result_messages, {"role": "user", "content": nudge}]},
                    {"recursion_limit": _RECURSION_LIMIT},
                )
                result_messages = result["messages"]
                structured_response = result.get("structured_response")

            shortfalls = _all_shortfalls(job_name, require_tools, require_tool_counts, result_messages)
            if shortfalls:
                raise RuntimeError(
                    f"job {job_name} still incomplete after {_MAX_FOLLOWUPS} follow-ups: "
                    + "; ".join(shortfalls)
                )

            # The writes are done but the model may have ended on a silent tool call
            # with no prose and no structured_response (common with Ollama). Ask once,
            # explicitly, for a plain-text wrap-up so the agent_runs row is meaningful.
            if structured_response is None and not _last_assistant_text(result_messages):
                logger.info("Job %s made its writes but produced no summary; requesting one", job_name)
                result = await agent.ainvoke(
                    {"messages": [*result_messages, {"role": "user", "content": (
                        "Reply now in plain text — no more tool calls — with a 2 to 3 sentence "
                        "summary of what you saved and whether the notification email was sent "
                        "(say so explicitly if it was skipped)."
                    )}]},
                    {"recursion_limit": _RECURSION_LIMIT},
                )
                result_messages = result["messages"]
                structured_response = result.get("structured_response")

        if remember:
            await save_history(session_id, result_messages, settings)

        if trace:
            return _format_trace(result_messages)
        if structured_response is not None:
            if isinstance(structured_response, BaseModel):
                return structured_response.model_dump_json()
            return str(structured_response)
        return _final_text(result_messages)
    finally:
        await dispose_model(model)


def _tool_call_counts(messages: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for message in messages:
        for call in getattr(message, "tool_calls", None) or []:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
            if name:
                counts[name] = counts.get(name, 0) + 1
    return counts


def _called_tool_names(messages: list[Any]) -> set[str]:
    return set(_tool_call_counts(messages))


def _tool_shortfalls(
    require_tools: list[str | tuple[str, ...]] | None,
    require_tool_counts: dict[str, int] | None,
    messages: list[Any],
) -> list[str]:
    """Human-readable list of what the run still owes: uncalled required tools and
    required tools called fewer times than expected (e.g. 22/28 menu slots saved)."""
    counts = _tool_call_counts(messages)
    shortfalls: list[str] = []
    for name in require_tools or []:
        if isinstance(name, tuple):
            if not any(counts.get(alt) for alt in name):
                shortfalls.append(f"call one of {', '.join(name)}")
            continue
        if name not in (require_tool_counts or {}) and not counts.get(name):
            shortfalls.append(f"call {name}")
    for name, needed in (require_tool_counts or {}).items():
        have = counts.get(name, 0)
        if have < needed:
            shortfalls.append(f"call {name} for the remaining {needed - have} of {needed}")
    return shortfalls


_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_MEALS = ("breakfast", "lunch", "snack", "dinner")
_ALL_MENU_SLOTS = {(day, meal) for day in _WEEKDAYS for meal in _MEALS}


def _weekly_menu_slot_shortfall(messages: list[Any]) -> list[str]:
    """The distinct (day, meal) slots the weekly_menu run still hasn't saved.

    `_tool_shortfalls` only counts *how many* add_weekly_menu_item calls were made, so
    a run that re-saved five weekday slots eight times reaches 28 calls while Saturday
    and Sunday stay untouched. This checks the actual arguments and requires all 28
    distinct Monday-Sunday slots.
    """
    saved: set[tuple[str, str]] = set()
    for message in messages:
        for call in getattr(message, "tool_calls", None) or []:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
            if name != "add_weekly_menu_item":
                continue
            args = call.get("args") if isinstance(call, dict) else getattr(call, "args", None)
            if not isinstance(args, dict):
                continue
            slot = (
                str(args.get("day_of_week", "")).strip().lower(),
                str(args.get("meal_type", "")).strip().lower(),
            )
            if slot in _ALL_MENU_SLOTS:
                saved.add(slot)
    missing = _ALL_MENU_SLOTS - saved
    if not missing:
        return []
    preview = ", ".join(f"{day} {meal}" for day, meal in sorted(missing))
    return [f"save the {len(missing)} still-missing day/meal slot(s): {preview}"]


def _all_shortfalls(
    job_name: str | None,
    require_tools: list[str | tuple[str, ...]] | None,
    require_tool_counts: dict[str, int] | None,
    messages: list[Any],
) -> list[str]:
    shortfalls = _tool_shortfalls(require_tools, require_tool_counts, messages)
    if job_name == "weekly_menu":
        shortfalls += _weekly_menu_slot_shortfall(messages)
    return shortfalls


def _last_assistant_text(messages: list[Any]) -> str:
    """The most recent non-empty assistant message text, or "" if there is none."""
    for message in reversed(messages):
        if type(message).__name__ in {"AIMessage", "AIMessageChunk"}:
            text = _message_text(message).strip()
            if text:
                return text
    return ""


def _final_text(messages: list[Any]) -> str:
    """The agent's reply, with a fallback so a job/telemetry row is never blank.

    A model that ends its turn on a tool call (common for the scheduled jobs, whose
    last instruction is "send the email") can leave the final message with empty
    content. Fall back to the most recent non-empty assistant text, and if there is
    none, a short recap of the tools it called so the agent_runs log still says what
    happened.
    """
    text = _last_assistant_text(messages)
    if text:
        return text
    tool_calls = _called_tool_names(messages)
    if tool_calls:
        return "Completed with no closing summary. Tools called: " + ", ".join(sorted(tool_calls)) + "."
    return "Completed with no output."


async def _stream_agent(agent: Any, messages: list[dict[str, str]]) -> list[Any]:
    """Stream model/tool events while retaining the final agent state."""
    result_messages: list[Any] | None = None
    async for event in agent.astream_events({"messages": messages}, version="v2"):
        event_name = event.get("event", "")
        event_data = event.get("data", {})

        if event_name == "on_chat_model_stream":
            chunk = event_data.get("chunk")
            if chunk is not None:
                _log_stream_chunk(chunk)
        elif event_name == "on_tool_start":
            logger.info("[tool start] %s input=%s", event.get("name"), event_data.get("input"))
        elif event_name == "on_tool_end":
            logger.info("[tool end] %s output=%s", event.get("name"), event_data.get("output"))
        elif event_name == "on_chain_end":
            output = event_data.get("output")
            if isinstance(output, dict) and isinstance(output.get("messages"), list):
                result_messages = output["messages"]

    if result_messages is None:
        raise RuntimeError("Agent stream ended without a final message state")
    return result_messages


def _log_stream_chunk(chunk: Any) -> None:
    """Log only reasoning/text explicitly emitted by the model provider."""
    content_blocks = getattr(chunk, "content_blocks", None) or []
    if not content_blocks:
        content = getattr(chunk, "content", "")
        content_blocks = content if isinstance(content, list) else [{"type": "text", "text": content}]

    for block in content_blocks:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type", "text")
        value = block.get("reasoning", block.get("text", ""))
        if value:
            logger.info("[model %s] %s", block_type, value)


def _format_trace(messages: list[Any]) -> str:
    sections = []
    for message in messages:
        message_type = type(message).__name__
        details = [f"[{message_type}]"]
        text = _message_text(message).strip()
        if text:
            details.append(text)
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            details.append(f"tool_calls={tool_calls}")
        content_blocks = getattr(message, "content_blocks", None) or []
        reasoning = [
            block.get("reasoning", block.get("text", ""))
            for block in content_blocks
            if isinstance(block, dict) and block.get("type") in {"reasoning", "thinking"}
        ]
        if reasoning:
            details.append(f"reasoning={' '.join(reasoning)}")
        sections.append("\n".join(details))
    return "\n\n".join(sections)


def _message_text(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    return "".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type", "text") == "text"
    )
