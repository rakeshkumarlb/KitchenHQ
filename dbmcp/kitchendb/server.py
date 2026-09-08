"""The FastAPI application factory: lifespan, API-key middleware, REST routes, MCP app.

``create_app()`` builds a fresh FastMCP instance (its streamable-HTTP session manager
can only be run once per instance, so tests need a new one per case) and a fresh
FastAPI app. ``app`` is the module-level instance used in production
(``uvicorn init_db:app``).
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from .config import API_KEY_HEADER, PUBLIC_PATHS, mcp_allowed_hosts
from .routes import router
from .schema import initialize_database
from .tools import registered_tools


def build_mcp() -> FastMCP:
    mcp = FastMCP(
        "KitchenHQ Database",
        transport_security=TransportSecuritySettings(allowed_hosts=mcp_allowed_hosts()),
    )
    for fn in registered_tools():
        mcp.add_tool(fn)
    return mcp


def create_app() -> FastAPI:
    mcp = build_mcp()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if not os.environ.get("KITCHENHQ_API_KEY"):
            raise RuntimeError("KITCHENHQ_API_KEY must be set")
        initialize_database()
        async with mcp.session_manager.run():
            yield

    application = FastAPI(title="KitchenHQ Database Tools", lifespan=lifespan)

    @application.middleware("http")
    async def require_api_key(request: Request, call_next):
        if request.url.path not in PUBLIC_PATHS and request.headers.get(API_KEY_HEADER) != os.environ.get("KITCHENHQ_API_KEY"):
            return JSONResponse({"detail": "Invalid or missing API key"}, status_code=401)
        return await call_next(request)

    application.include_router(router)
    # Mounted last so it is the catch-all fallback after every /api/* route.
    application.mount("/", mcp.streamable_http_app())
    return application


app = create_app()
