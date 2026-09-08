from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

from .config import Settings

logger = logging.getLogger("kitchenhq-agent")


async def load_tools(settings: Settings) -> list[Any]:
    """Connect to the KitchenHQ MCP server and return every available tool.

    All roles get the full toolset; role boundaries are enforced by the system prompt
    (see app/prompts.py), not by filtering which tools an agent can see. A fresh
    `MultiServerMCPClient` is built per call; `get_tools()` already opens and closes
    its own MCP session, so there is nothing left to explicitly tear down here.
    """
    client = MultiServerMCPClient(
        {
            "kitchenhq": {
                "transport": settings.mcp_transport,
                "url": settings.mcp_url,
                "headers": {"X-API-Key": settings.kitchenhq_api_key},
            }
        }
    )
    for attempt in range(1, settings.mcp_connect_retries + 1):
        try:
            return await client.get_tools()
        except Exception:
            if attempt == settings.mcp_connect_retries:
                raise
            logger.warning(
                "MCP is not ready (attempt %d/%d); retrying in %.1fs",
                attempt, settings.mcp_connect_retries, settings.mcp_connect_delay,
            )
            await asyncio.sleep(settings.mcp_connect_delay)
    raise AssertionError("unreachable")
