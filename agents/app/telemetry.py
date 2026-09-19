from __future__ import annotations

import logging

import httpx

from .config import Settings

logger = logging.getLogger("kitchenhq-agent")


async def record_agent_run(
    role: str, job_name: str, status: str, settings: Settings, *,
    result: str = "", error: str = "",
    context_length: int | None = None, input_tokens: int | None = None,
    output_tokens: int | None = None, total_tokens: int | None = None,
) -> None:
    """Best-effort operational telemetry; a telemetry outage must not fail the caller.

    The token/context fields are themselves best-effort (see kitchen_agent.AgentReply) -
    `None` here just means the provider didn't report usage_metadata for this run, not
    an error."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(
                f"{settings.db_api_url}/api/agent-runs",
                json={
                    "agent_role": role, "job_name": job_name, "status": status, "result": result, "error": error,
                    "context_length": context_length, "input_tokens": input_tokens,
                    "output_tokens": output_tokens, "total_tokens": total_tokens,
                },
                headers={"X-API-Key": settings.kitchenhq_api_key},
            )
            response.raise_for_status()
    except Exception:
        logger.warning("Could not persist agent run telemetry", exc_info=True)
