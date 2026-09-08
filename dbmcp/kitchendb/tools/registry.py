"""A tiny decorator that collects the MCP-exposed data operations.

`@tool` records a function as an MCP tool and returns it unchanged, so the same
function is still a plain callable that routes.py can import and call directly. The
FastMCP instance is built later, per app, in kitchendb/server.create_app() - nothing
here is bound to a specific server instance.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

_REGISTRY: list[Callable] = []

F = TypeVar("F", bound=Callable)


def tool(fn: F) -> F:
    _REGISTRY.append(fn)
    return fn


def registered_tools() -> tuple[Callable, ...]:
    return tuple(_REGISTRY)
