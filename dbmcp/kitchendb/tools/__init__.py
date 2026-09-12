"""Every data operation, split by domain.

Importing this package imports each domain module, which populates the tool registry
(kitchendb/tools/registry.py) via the ``@tool`` decorator. kitchendb/server.create_app()
then builds one FastMCP instance and registers ``registered_tools()`` on it.

Each function is also a plain callable - kitchendb/routes.py imports the same functions
to build the REST surface, so a data operation is written once and exposed twice.

Not every function here is an MCP tool: ``cancel_prep_schedule``,
``acknowledge_shopping_items``, ``get_user_profile`` and ``update_user_profile`` are
REST-only (human actions, not agent ones) and carry no ``@tool``.
"""

from __future__ import annotations

from .registry import registered_tools

# Imported for their registration side effect.
from . import inventory, weekly_menu, prep, shopping, profile, audit  # noqa: E402,F401

__all__ = ["registered_tools"]
