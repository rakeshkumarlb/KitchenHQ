from __future__ import annotations

import logging
from typing import Any

import httpx
from langchain_core.messages import messages_from_dict, messages_to_dict

from .config import Settings

logger = logging.getLogger("kitchenhq-agent")


def _headers(settings: Settings) -> dict[str, str]:
    return {"X-API-Key": settings.kitchenhq_api_key}


async def load_history(session_id: str, settings: Settings) -> list[Any]:
    """Fetch a session's chat history from dbmcp; empty on any failure or first use."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{settings.db_api_url}/api/chat-sessions/{session_id}",
                headers=_headers(settings),
            )
            response.raise_for_status()
        return messages_from_dict(response.json()["messages"])
    except Exception:
        logger.warning("Could not load chat history for session %s", session_id, exc_info=True)
        return []


async def save_history(session_id: str, messages: list[Any], settings: Settings) -> None:
    """Persist a session's chat history to dbmcp; a storage outage must not fail the turn."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.put(
                f"{settings.db_api_url}/api/chat-sessions/{session_id}",
                json={"messages": messages_to_dict(messages)},
                headers=_headers(settings),
            )
            response.raise_for_status()
    except Exception:
        logger.warning("Could not persist chat history for session %s", session_id, exc_info=True)
