"""Standalone interactive terminal chat with the Executive Chef.

Runs the same `run_agent()` used by agent-api, in-process, so this works without
agent-api or Docker running - just `dbmcp` reachable at MCP_URL. Each turn still
builds and disposes its own model/MCP connections, same as a real request would.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))
load_dotenv(".env", override=False)
load_dotenv(".env.local", override=False)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("kitchenhq-agent")

from app.config import load_settings  # noqa: E402
from app.kitchen_agent import run_agent  # noqa: E402


async def interactive_chat() -> None:
    settings = load_settings()
    show_trace = os.getenv("SHOW_AGENT_TRACE", "true").lower() in {"1", "true", "yes", "on"}
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
            reply = await run_agent("executive_chef", text, settings, trace=show_trace)
            print(f"Chef: {reply}")
        except Exception as error:
            logger.exception("Interactive request failed")
            print(f"Chef error: {error}")


if __name__ == "__main__":
    asyncio.run(interactive_chat())
