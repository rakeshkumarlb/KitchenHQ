"""Central place for every environment variable this service reads.

Settings are loaded fresh per request/job (see `kitchen_agent.run_agent`) rather than
cached at import time, so a config reload never requires a process restart.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    kitchenhq_api_key: str
    db_api_url: str
    mcp_url: str
    mcp_transport: str
    mcp_connect_retries: int
    mcp_connect_delay: float
    llm_provider: str
    llm_model: str
    llm_temperature: float
    ollama_base_url: str
    ollama_api_key: str | None
    openai_api_key: str | None
    tz: str


def load_settings() -> Settings:
    api_key = os.getenv("KITCHENHQ_API_KEY")
    if not api_key:
        raise RuntimeError("KITCHENHQ_API_KEY must be set")
    return Settings(
        kitchenhq_api_key=api_key,
        db_api_url=os.getenv("DB_API_URL", "http://dbmcp:18000"),
        mcp_url=os.getenv("MCP_URL", "http://localhost:18000/mcp"),
        mcp_transport=os.getenv("MCP_TRANSPORT", "streamable_http"),
        mcp_connect_retries=int(os.getenv("MCP_CONNECT_RETRIES", "12")),
        mcp_connect_delay=float(os.getenv("MCP_CONNECT_DELAY", "2")),
        llm_provider=os.getenv("LLM_PROVIDER", "ollama").lower(),
        llm_model=os.getenv("LLM_MODEL", "gemma4"),
        llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_api_key=os.getenv("OLLAMA_API_KEY"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        tz=os.getenv("TZ", "UTC"),
    )
