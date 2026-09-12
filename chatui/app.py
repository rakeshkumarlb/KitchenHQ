from __future__ import annotations

import os
from uuid import UUID, uuid4
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import httpx


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: UUID = Field(default_factory=uuid4)


class ChatResponse(BaseModel):
    reply: str
    session_id: UUID


app = FastAPI(title="KitchenHQ Chat UI")
DB_API_URL = os.environ.get("DB_API_URL", "http://dbmcp:18000")
AGENT_API_URL = os.environ.get("AGENT_API_URL", "http://agent-api:8090")
API_KEY_HEADER = "X-API-Key"
PUBLIC_PATHS = {"/api/health"}


@app.middleware("http")
async def require_api_key(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.url.path not in PUBLIC_PATHS:
        if request.headers.get(API_KEY_HEADER) != os.environ.get("KITCHENHQ_API_KEY"):
            return JSONResponse({"detail": "Invalid or missing API key"}, status_code=401)
    return await call_next(request)


@app.get("/", response_class=FileResponse)
async def index() -> FileResponse:
    return FileResponse(Path(__file__).with_name("dist") / "index.html")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ready"}


async def _proxy(base_url: str, method: str, path: str, payload: dict | None = None, *, timeout: float = 10) -> dict:
    headers = {API_KEY_HEADER: os.environ.get("KITCHENHQ_API_KEY", "")}
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(method, f"{base_url}{path}", json=payload, headers=headers)
    if response.is_error:
        try:
            detail = response.json().get("detail", "Upstream service unavailable")
        except ValueError:
            # Upstream returned a non-JSON error body (e.g. an unhandled exception's
            # plain-text 500) - never let that crash this proxy too, or the browser
            # sees an opaque "Unexpected token" JSON-parse error instead of a real detail.
            detail = "Upstream service unavailable"
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()


async def db_request(method: str, path: str, payload: dict | None = None) -> dict:
    return await _proxy(DB_API_URL, method, path, payload)


async def agent_request(method: str, path: str, payload: dict | None = None, *, timeout: float = 120) -> dict:
    return await _proxy(AGENT_API_URL, method, path, payload, timeout=timeout)


@app.get("/api/dashboard")
async def dashboard() -> dict:
    return await db_request("GET", "/api/dashboard")


@app.get("/api/profile")
async def get_profile() -> dict:
    return await db_request("GET", "/api/profile")


@app.put("/api/profile")
async def update_profile(payload: dict) -> dict:
    return await db_request("PUT", "/api/profile", payload)


@app.get("/api/household-members")
async def list_household_members() -> list[dict]:
    return await db_request("GET", "/api/household-members")


@app.post("/api/household-members")
async def add_household_member(payload: dict) -> dict:
    return await db_request("POST", "/api/household-members", payload)


@app.put("/api/household-members/{member_id}")
async def update_household_member(member_id: int, payload: dict) -> dict:
    return await db_request("PUT", f"/api/household-members/{member_id}", payload)


@app.delete("/api/household-members/{member_id}")
async def delete_household_member(member_id: int) -> dict:
    return await db_request("DELETE", f"/api/household-members/{member_id}")


# soft-deleted: no caller. The chatui Pantry page is read-only now, so nothing hits
# these inventory-mutation proxies. The dbmcp routes/MCP tools behind them stay.
#
# @app.patch("/api/inventory/{item_id}")
# async def adjust_inventory(item_id: int, payload: dict) -> dict:
#     return await db_request("PATCH", f"/api/inventory/{item_id}", payload)
#
# @app.post("/api/inventory/{item_id}/discard")
# async def discard_inventory(item_id: int, payload: dict) -> dict:
#     return await db_request("POST", f"/api/inventory/{item_id}/discard", payload)


@app.post("/api/shopping-items")
async def add_shopping_items(payload: dict) -> dict:
    return await db_request("POST", "/api/shopping-items", payload)


@app.patch("/api/shopping-items/{shopping_item_id}")
async def edit_shopping_item(shopping_item_id: int, payload: dict) -> dict:
    return await db_request("PATCH", f"/api/shopping-items/{shopping_item_id}", payload)


@app.delete("/api/shopping-items/{shopping_item_id}")
async def delete_shopping_item(shopping_item_id: int) -> dict:
    return await db_request("DELETE", f"/api/shopping-items/{shopping_item_id}")


@app.post("/api/shopping-items/acknowledge")
async def acknowledge_shopping(payload: dict) -> dict:
    return await db_request("POST", "/api/shopping-items/acknowledge", payload)


@app.patch("/api/prep-schedule/{task_id}/completion")
async def complete_task(task_id: int, payload: dict) -> dict:
    return await db_request("PATCH", f"/api/prep-schedule/{task_id}/completion", payload)


@app.post("/api/prep-schedule/{task_id}/cancel")
async def cancel_task(task_id: int, payload: dict | None = None) -> dict:
    return await db_request("POST", f"/api/prep-schedule/{task_id}/cancel", payload or {})


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    result = await agent_request(
        "POST",
        "/chat",
        {"message": request.message.strip(), "session_id": str(request.session_id)},
    )
    return ChatResponse(**result)


@app.get("/api/chat-sessions")
async def list_chat_sessions() -> list[dict]:
    return await db_request("GET", "/api/chat-sessions?limit=5")


@app.get("/api/chat-sessions/{session_id}")
async def get_chat_session(session_id: str) -> dict:
    raw = await db_request("GET", f"/api/chat-sessions/{session_id}")
    messages = []
    for entry in raw.get("messages", []):
        role = {"human": "user", "ai": "assistant"}.get(entry.get("type"))
        content = entry.get("data", {}).get("content", "")
        if role and content:
            messages.append({"role": role, "content": content})
    return {"session_id": session_id, "messages": messages}


@app.get("/api/automations/jobs")
async def list_automation_jobs() -> list[str]:
    return await agent_request("GET", "/jobs")


@app.get("/api/automations/runs")
async def list_automation_runs() -> list[dict]:
    return await db_request("GET", "/api/agent-runs")


@app.post("/api/automations/invoke/{job_name}")
async def invoke_automation(job_name: str) -> dict:
    return await agent_request("POST", f"/invoke/{job_name}", timeout=300)


app.mount("/", StaticFiles(directory=Path(__file__).with_name("dist"), html=True), name="chatui")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8080, reload=False)
