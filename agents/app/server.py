"""KitchenHQ agent-api: the only process that talks to the LLM and the MCP server.

Serves chat for chatui, on-demand job invocation ("run now" from chatui's Automations
page), and runs the same 5 cron jobs `worker.py` used to run - all in one FastAPI app,
so there is exactly one place that builds and disposes model/MCP connections.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
load_dotenv(".env", override=False)
load_dotenv(".env.local", override=False)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("kitchenhq-agent")

from .config import load_settings  # noqa: E402
from .jobs import SCHEDULED_REQUESTS, run_job  # noqa: E402
from .kitchen_agent import run_agent  # noqa: E402
from .scheduler import configure_scheduler  # noqa: E402

API_KEY_HEADER = "X-API-Key"
PUBLIC_PATHS = {"/health"}

# One lock per chat session so concurrent turns on the same session can't race on
# history read-modify-write; unrelated sessions still run fully concurrently.
_session_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    scheduler = configure_scheduler(settings)
    scheduler.start()
    logger.info("Autonomous scheduler started in timezone %s", settings.tz)
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(title="KitchenHQ Agent API", lifespan=lifespan)


@app.middleware("http")
async def require_api_key(request: Request, call_next):
    if request.url.path not in PUBLIC_PATHS:
        if request.headers.get(API_KEY_HEADER) != os.environ.get("KITCHENHQ_API_KEY"):
            return JSONResponse({"detail": "Invalid or missing API key"}, status_code=401)
    return await call_next(request)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: UUID = Field(default_factory=uuid4)


class ChatResponse(BaseModel):
    reply: str
    session_id: UUID


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ready"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    settings = load_settings()
    session_key = str(request.session_id)
    async with _session_locks[session_key]:
        try:
            reply = await run_agent(
                "executive_chef",
                request.message.strip(),
                settings,
                session_id=session_key,
                trace=False,
            )
        except Exception as error:
            raise HTTPException(status_code=502, detail=f"Chef service unavailable: {error}") from error
    return ChatResponse(reply=reply, session_id=request.session_id)


@app.get("/jobs")
async def list_jobs() -> list[str]:
    return sorted(SCHEDULED_REQUESTS)


@app.post("/invoke/{job_name}")
async def invoke_job(job_name: str) -> dict[str, str]:
    if job_name not in SCHEDULED_REQUESTS:
        raise HTTPException(status_code=404, detail=f"Unknown job: {job_name}")
    settings = load_settings()
    try:
        result = await run_job(job_name, settings)
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return {"job_name": job_name, "status": "completed", "result": result}
