"""Standalone Executive Chef agent for KitchenHQ.

The process serves two workloads at once:
* an interactive terminal conversation for ad-hoc requests; and
* recurring jobs that ask the same agent to maintain menus and prep tasks.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import messages_from_dict, messages_to_dict
from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import BaseModel, Field

try:
    from langchain_ollama import ChatOllama
except ImportError:
    ChatOllama = None

from langchain_openai import ChatOpenAI


load_dotenv(Path(__file__).with_name(".env"))
load_dotenv(".env", override=False)
load_dotenv(".env.local", override=False)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("kitchenhq-agent")

DB_API_URL = os.getenv("DB_API_URL", "http://dbmcp:18000")


def _db_api_headers() -> dict[str, str]:
    return {"X-API-Key": os.getenv("KITCHENHQ_API_KEY", "")}


async def _load_history(session_id: str) -> list[Any]:
    """Fetch a session's chat history from dbmcp; empty on any failure or first use."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{DB_API_URL}/api/chat-sessions/{session_id}", headers=_db_api_headers())
            response.raise_for_status()
        return messages_from_dict(response.json()["messages"])
    except Exception:
        logger.warning("Could not load chat history for session %s", session_id, exc_info=True)
        return []


async def _save_history(session_id: str, messages: list[Any]) -> None:
    """Persist a session's chat history to dbmcp; a storage outage must not fail the turn."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.put(
                f"{DB_API_URL}/api/chat-sessions/{session_id}",
                json={"messages": messages_to_dict(messages)},
                headers=_db_api_headers(),
            )
            response.raise_for_status()
    except Exception:
        logger.warning("Could not persist chat history for session %s", session_id, exc_info=True)


PROMPT_PATH = Path(__file__).with_name("prompt.md")
SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8") + """

Operating rules:
- Always query the relevant MCP table before making claims about current stock, menus, or tasks.
- Use the MCP write tools when the request says to save, record, update, or log something.
- For scheduled jobs, complete the requested database writes autonomously and report the result.
- If a request is ambiguous, ask one concise clarifying question instead of inventing database facts.
- For interactive conversations, be detailed and conversational: explain your reasoning, summarize relevant data, and give practical next steps. Use headings and bullets when they improve readability.

Supported ad-hoc work:
- Inventory: search stock, identify reorder items, upsert quantities, and log wastage.
- Executive chef: generate and save macro-balanced Monday-Friday menus using available inventory. Build the full proposal first, validate it with validate_weekly_menu_policy, then save it atomically with add_weekly_menu_plan; never save a partial plan through repeated single-item writes.
- Sous-chef: create and save Sunday, nightly, and morning prep tasks, then acknowledge them when reported.
- Feedback: record ratings and notes against the matching saved menu item.
- Recipes: query inventory first and create a random macro-balanced recipe from available ingredients.
"""

ROLE_PROMPTS = {
    "executive_chef": """
You are the Executive Chef agent. You are conversational and user-facing.
Focus on preferences, nutrition targets, weekly meal planning, recipes, substitutions, and menu feedback.
Do not create prep schedules or shopping lists unless the user explicitly asks for one.
When planning lunches, enforce all school restrictions supplied by the household.
""",
    "sous_chef": """
You are the Sous Chef agent. You are an autonomous planning specialist.
Read the active meal plan and create practical morning and nightly prep schedules with ordered, step-by-step instructions.
Every consumed ingredient must include an explicit inventory identifier, quantity, and unit. Never deduct inventory yourself.
""",
    "pantry_manager": """
You are the Pantry Manager agent. You are an autonomous inventory specialist.
Inspect current inventory, thresholds, open shopping lists, and upcoming meals, then create a shopping list proposal.
Never acknowledge purchases and never mutate inventory during a recommendation run.
""",
}

ROLE_TOOLS = {
    "executive_chef": None,
    "sous_chef": {"get_inventory", "get_weekly_menu", "get_prep_schedules", "add_detailed_prep_schedule"},
    "pantry_manager": {"get_inventory", "get_weekly_menu", "get_shopping_lists", "create_shopping_list"},
}


class SousChefResult(BaseModel):
    summary: str = Field(description="Short description of the prep schedules created")
    prep_schedule_ids: list[int] = Field(default_factory=list)


class PantryManagerResult(BaseModel):
    summary: str = Field(description="Short explanation of the shopping recommendation")
    shopping_list_id: int | None = None


def _build_model() -> Any:
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    model = os.getenv("LLM_MODEL", "gemma4")
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.2"))

    if provider == "ollama":
        if ChatOllama is None:
            raise RuntimeError("Install langchain-ollama to use LLM_PROVIDER=ollama")
        return ChatOllama(
            model=model,
            temperature=temperature,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            key=os.getenv("OLLAMA_API_KEY"),
        )

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY must be set when LLM_PROVIDER=openai")
    return ChatOpenAI(model=model, temperature=temperature)


class KitchenHQAgent:
    """One LangChain agent connected to the KitchenHQ MCP server."""

    def __init__(self, role: str = "executive_chef") -> None:
        if role not in ROLE_PROMPTS:
            raise ValueError(f"Unsupported agent role: {role}")
        self.role = role
        self.model = _build_model()
        api_key = os.getenv("KITCHENHQ_API_KEY")
        if not api_key:
            raise RuntimeError("KITCHENHQ_API_KEY must be set")
        self.client = MultiServerMCPClient(
            {
                "kitchenhq": {
                    "transport": os.getenv("MCP_TRANSPORT", "streamable_http"),
                    "url": os.getenv("MCP_URL", "http://localhost:18000/mcp"),
                    "headers": {"X-API-Key": api_key},
                }
            }
        )
        self._agent = None
        self._agent_lock = asyncio.Lock()

    async def start(self) -> None:
        retries = int(os.getenv("MCP_CONNECT_RETRIES", "12"))
        delay = float(os.getenv("MCP_CONNECT_DELAY", "2"))
        tools = None
        for attempt in range(1, retries + 1):
            try:
                tools = await self.client.get_tools()
                break
            except Exception:
                if attempt == retries:
                    raise
                logger.warning("MCP is not ready (attempt %d/%d); retrying in %.1fs", attempt, retries, delay)
                await asyncio.sleep(delay)
        allowed_tools = ROLE_TOOLS[self.role]
        if allowed_tools is not None:
            tools = [tool for tool in tools if tool.name.rsplit("__", 1)[-1] in allowed_tools]
        response_format = {
            "sous_chef": SousChefResult,
            "pantry_manager": PantryManagerResult,
        }.get(self.role)
        agent_options = {"response_format": response_format} if response_format else {}
        self._agent = create_agent(
            model=self.model,
            tools=tools,
            system_prompt=SYSTEM_PROMPT + "\n\nRole boundary:\n" + ROLE_PROMPTS[self.role],
            **agent_options,
        )
        logger.info("Connected to KitchenHQ MCP at %s with %d tools", os.getenv("MCP_URL", "http://localhost:8000/mcp"), len(tools))

    async def ask(
        self,
        text: str,
        *,
        session_id: str = "default",
        remember: bool = True,
        trace: bool = True,
    ) -> str:
        if self._agent is None:
            raise RuntimeError("Agent has not been started")
        async with self._agent_lock:
            history = await _load_history(session_id) if remember else []
            messages = [*history, {"role": "user", "content": text}]
            if trace:
                result_messages = await self._stream_agent(messages)
                structured_response = None
            else:
                result = await self._agent.ainvoke({"messages": messages})
                result_messages = result["messages"]
                structured_response = result.get("structured_response")
            if remember:
                await _save_history(session_id, result_messages)
            if trace:
                return self._format_trace(result_messages)
            if structured_response is not None:
                if isinstance(structured_response, BaseModel):
                    return structured_response.model_dump_json()
                return str(structured_response)
            return self._message_text(result_messages[-1])

    async def _stream_agent(self, messages: list[dict[str, str]]) -> list[Any]:
        """Stream model/tool events while retaining the final agent state."""
        result_messages: list[Any] | None = None
        async for event in self._agent.astream_events(
            {"messages": messages},
            version="v2",
        ):
            event_name = event.get("event", "")
            event_data = event.get("data", {})

            if event_name == "on_chat_model_stream":
                chunk = event_data.get("chunk")
                if chunk is not None:
                    self._log_stream_chunk(chunk)
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

    @staticmethod
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

    @classmethod
    def _format_trace(cls, messages: list[Any]) -> str:
        sections = []
        for message in messages:
            message_type = type(message).__name__
            details = [f"[{message_type}]"]
            text = cls._message_text(message).strip()
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

    @staticmethod
    def _message_text(message: Any) -> str:
        content = getattr(message, "content", message)
        if isinstance(content, str):
            return content
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type", "text") == "text"
        )


SCHEDULED_REQUESTS = {
    "weekly_menu": "Every Saturday: query inventory and feedback, then generate and save the complete Monday-Friday menu. Report the saved menu IDs.",
    "sunday_prep": "Every Sunday: query the saved weekly menu and create and save a Sunday batch-prep plan of no more than 60 minutes.",
    "nightly_prep": "Tonight: query tomorrow's menu and save a practical prep task that takes no more than 10 minutes.",
    "morning_prep": "This morning: query today's menu and save a parallel cooking plan capped at 20 minutes.",
    "pantry_manager": "Today at 18:00: query current inventory and the upcoming menu, calculate items below optimal stock, and save a shopping list proposal. Never change inventory for this job.",
}


async def run_scheduled(agent: KitchenHQAgent, job_name: str) -> None:
    request = SCHEDULED_REQUESTS[job_name]
    logger.info("Running scheduled job: %s", job_name)
    try:
        result = await agent.ask(request, remember=False)
        result_models = {
            "sunday_prep": SousChefResult,
            "nightly_prep": SousChefResult,
            "morning_prep": SousChefResult,
            "pantry_manager": PantryManagerResult,
        }
        result_model = result_models.get(job_name)
        if result_model is not None:
            result_model.model_validate(json.loads(result))
        logger.info("Scheduled job %s completed:\n%s", job_name, result)
        await _record_agent_run(agent, job_name, "completed", result=result)
    except Exception:
        logger.exception("Scheduled job %s failed", job_name)
        await _record_agent_run(agent, job_name, "failed", error="scheduled job failed; see worker logs")


async def _record_agent_run(agent: KitchenHQAgent, job_name: str, status: str, *, result: str = "", error: str = "") -> None:
    """Best-effort operational telemetry; a telemetry outage must not stop the worker."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(
                f"{DB_API_URL}/api/agent-runs",
                json={"agent_role": agent.role, "job_name": job_name, "status": status, "result": result, "error": error},
                headers=_db_api_headers(),
            )
            response.raise_for_status()
    except Exception:
        logger.warning("Could not persist agent run telemetry", exc_info=True)


def configure_scheduler(agent: KitchenHQAgent | dict[str, KitchenHQAgent]) -> AsyncIOScheduler:
    agents = agent if isinstance(agent, dict) else {"executive_chef": agent, "sous_chef": agent, "pantry_manager": agent}
    timezone = os.getenv("TZ", "UTC")
    scheduler = AsyncIOScheduler(timezone=timezone)
    scheduler.add_job(run_scheduled, "cron", day_of_week="sat", hour=10, minute=0, args=[agents["executive_chef"], "weekly_menu"], id="weekly-menu", replace_existing=True)
    scheduler.add_job(run_scheduled, "cron", day_of_week="sun", hour=14, minute=0, args=[agents["sous_chef"], "sunday_prep"], id="sunday-prep", replace_existing=True)
    scheduler.add_job(run_scheduled, "cron", day_of_week="sun,mon,tue,wed,thu", hour=20, minute=0, args=[agents["sous_chef"], "nightly_prep"], id="nightly-prep", replace_existing=True)
    scheduler.add_job(run_scheduled, "cron", day_of_week="mon-fri", hour=6, minute=30, args=[agents["sous_chef"], "morning_prep"], id="morning-prep", replace_existing=True)
    scheduler.add_job(run_scheduled, "cron", hour=18, minute=0, args=[agents["pantry_manager"], "pantry_manager"], id="pantry-manager-daily", replace_existing=True)
    return scheduler


async def interactive_chat(agent: KitchenHQAgent) -> None:
    print("KitchenHQ Executive Chef ready. Type 'quit' to exit.")
    while True:
        try:
            text = await asyncio.to_thread(input, "You: ")
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if text.strip().lower() in {"quit", "exit"}:
            return
        if not text.strip():
            continue
        try:
            show_trace = os.getenv("SHOW_AGENT_TRACE", "true").lower() in {"1", "true", "yes", "on"}
            print(f"Chef: {await agent.ask(text, trace=show_trace)}")
        except Exception as error:
            logger.exception("Interactive request failed")
            print(f"Chef error: {error}")


async def main() -> None:
    agent = KitchenHQAgent()
    await agent.start()
    #scheduler = configure_scheduler(agent)
    #scheduler.start()
    #logger.info("Autonomous scheduler started in timezone %s", os.getenv("TZ", "UTC"))
    try:
        await interactive_chat(agent)
    finally:
        #scheduler.shutdown(wait=False)
        pass


if __name__ == "__main__":
    asyncio.run(main())