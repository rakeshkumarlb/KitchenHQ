from __future__ import annotations

import logging

import httpx

from .config import Settings

logger = logging.getLogger("kitchenhq-agent")


async def record_agent_run(
    role: str, job_name: str, status: str, settings: Settings, *, result: str = "", error: str = ""
) -> None:
    """Best-effort operational telemetry; a telemetry outage must not fail the caller."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(
                f"{settings.db_api_url}/api/agent-runs",
                json={"agent_role": role, "job_name": job_name, "status": status, "result": result, "error": error},
                headers={"X-API-Key": settings.kitchenhq_api_key},
            )
            response.raise_for_status()
    except Exception:
        logger.warning("Could not persist agent run telemetry", exc_info=True)
