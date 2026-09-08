"""Local email-notification tools for the kitchen agents.

Email used to live in dbmcp (SMTP send + body builders + three `send_*_email` MCP
tools). None of it needed the database directly, so it moved here: the agent is the
only process that sends mail, and the two bits of stored data an email needs (the
recipient profile, and the saved menu / shopping items used to back-fill an omitted
payload) are fetched over the dbmcp REST API.

One responsibility per module:
  - `schemas`  : Pydantic payload contracts + day/meal vocab (no I/O)
  - `smtp`     : SMTP transport + recipient resolution
  - `render`   : (payload dict) -> (subject, text_body, html_body)
  - `backfill` : fetch saved menu / shopping items from dbmcp REST
  - `tools`    : wire the three StructuredTools the agent gets each run
"""

from __future__ import annotations

from .tools import make_email_tools

__all__ = ["make_email_tools"]
