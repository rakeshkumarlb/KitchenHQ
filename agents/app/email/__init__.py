"""Local email-notification tools for the kitchen agents.

Email used to live in dbmcp (SMTP send + body builders + three `send_*_email` MCP
tools); it moved here because the agent is the only process that sends mail. The
agent passes the plan/list it just authored straight into the tool, which renders and
sends it. Two reads still go to the dbmcp REST API from here: the recipient (from the
household profile - never chosen by the model) and, only for the weekly-plan email,
the saved menu (that email summarizes a whole week and isn't an enforced job step).

One responsibility per module:
  - `schemas`  : Pydantic payload contracts + day/meal vocab (no I/O)
  - `smtp`     : SMTP transport + recipient resolution
  - `render`   : (payload dict) -> (subject, text_body, html_body)
  - `backfill` : fetch the saved menu for the weekly-plan email (only)
  - `tools`    : wire the three StructuredTools the agent gets each run
"""

from __future__ import annotations

from .tools import make_email_tools

__all__ = ["make_email_tools"]
