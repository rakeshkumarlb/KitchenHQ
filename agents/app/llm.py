"""Build and tear down the LLM client for a single request/job.

Root cause of the long-running Ollama lockups: `ChatOllama`/`ChatOpenAI` each hold a
persistent HTTP connection pool internally, and the previous code built exactly one
of these per agent process and kept it alive for days. A stale keep-alive connection
to Ollama would eventually get silently dropped and wedge further requests -
sometimes badly enough to affect Ollama access from anywhere else on the machine.

The fix: build a fresh model here for every call, and always dispose it afterwards
(see `dispose_model`) so nothing outlives a single request.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any

from langchain_openai import ChatOpenAI

try:
    from langchain_ollama import ChatOllama
except ImportError:
    ChatOllama = None

from .config import Settings

logger = logging.getLogger("kitchenhq-agent")


def build_model(settings: Settings) -> Any:
    if settings.llm_provider == "ollama":
        if ChatOllama is None:
            raise RuntimeError("Install langchain-ollama to use LLM_PROVIDER=ollama")
        return ChatOllama(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            base_url=settings.ollama_base_url,
            key=settings.ollama_api_key,
        )

    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY must be set when LLM_PROVIDER=openai")
    return ChatOpenAI(model=settings.llm_model, temperature=settings.llm_temperature)


async def dispose_model(model: Any) -> None:
    """Best-effort close of every HTTP client the model constructed internally."""
    for attr in ("_async_client", "async_client", "root_async_client"):
        client = getattr(model, attr, None)
        if client is None:
            continue
        closer = getattr(client, "aclose", None) or getattr(client, "close", None)
        if closer is None:
            continue
        try:
            result = closer()
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.debug("Error closing LLM async client", exc_info=True)

    for attr in ("_client", "client", "root_client"):
        client = getattr(model, attr, None)
        if client is None:
            continue
        closer = getattr(client, "close", None)
        if closer is None:
            continue
        try:
            closer()
        except Exception:
            logger.debug("Error closing LLM sync client", exc_info=True)
