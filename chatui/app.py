from __future__ import annotations

import os
import sys
from uuid import UUID, uuid4
from contextlib import asynccontextmanager
from pathlib import Path
from inspect import isawaitable

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "executivechef_agent"))
from agent import KitchenHQAgent  # noqa: E402


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: UUID = Field(default_factory=uuid4)


class ChatResponse(BaseModel):
    reply: str
    session_id: UUID


@asynccontextmanager
async def lifespan(app: FastAPI):
    agent = KitchenHQAgent()
    await agent.start()
    app.state.agent = agent
    try:
        yield
    finally:
        for method_name in ("close", "shutdown", "stop"):
            method = getattr(agent, method_name, None)
            if callable(method):
                result = method()
                if isawaitable(result):
                    await result
                break


app = FastAPI(title="KitchenHQ Executive Chef", lifespan=lifespan)
DB_API_URL = os.environ.get("DB_API_URL", "http://dbmcp:18000")


@app.get("/", response_class=FileResponse)
async def index() -> FileResponse:
    return FileResponse(Path(__file__).with_name("dist") / "index.html")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ready" if hasattr(app.state, "agent") else "starting"}


async def db_request(method: str, path: str, payload: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.request(method, f"{DB_API_URL}{path}", json=payload)
    if response.is_error:
        detail = response.json().get("detail", "Database service unavailable")
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()


@app.get("/api/dashboard")
async def dashboard() -> dict:
    return await db_request("GET", "/api/dashboard")


@app.patch("/api/inventory/{item_id}")
async def adjust_inventory(item_id: int, payload: dict) -> dict:
    return await db_request("PATCH", f"/api/inventory/{item_id}", payload)


@app.post("/api/inventory/{item_id}/discard")
async def discard_inventory(item_id: int, payload: dict) -> dict:
    return await db_request("POST", f"/api/inventory/{item_id}/discard", payload)


@app.post("/api/shopping-lists")
async def create_shopping_list(payload: dict) -> dict:
    return await db_request("POST", "/api/shopping-lists", payload)


@app.post("/api/shopping-lists/{shopping_list_id}/acknowledge")
async def acknowledge_shopping(shopping_list_id: int, payload: dict) -> dict:
    return await db_request("POST", f"/api/shopping-lists/{shopping_list_id}/acknowledge", payload)


@app.post("/api/weekly-menu/{menu_item_id}/rating")
async def rate_menu(menu_item_id: int, payload: dict) -> dict:
    return await db_request("POST", f"/api/weekly-menu/{menu_item_id}/rating", payload)


@app.patch("/api/prep-schedule/{task_id}/completion")
async def complete_task(task_id: int, payload: dict) -> dict:
    return await db_request("PATCH", f"/api/prep-schedule/{task_id}/completion", payload)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    try:
        reply = await app.state.agent.ask(
            request.message.strip(),
            session_id=str(request.session_id),
            trace=False,
        )
        return ChatResponse(reply=reply, session_id=request.session_id)
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Chef service unavailable: {error}") from error


app.mount("/", StaticFiles(directory=Path(__file__).with_name("dist"), html=True), name="chatui")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8080, reload=False)
