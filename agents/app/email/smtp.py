"""SMTP transport + recipient resolution. The only module here that does network I/O
for sending; body content comes from `render`, contracts from `schemas`.

Delivery is best-effort: a broken/unset mailbox returns ``{"sent": False, ...}`` so a
scheduled job is never failed by an email problem. Config is entirely environment
driven (``SMTP_HOST`` etc.); with ``SMTP_HOST`` unset the feature is inert.
"""

from __future__ import annotations

import logging
import os
import re
import smtplib
from email.message import EmailMessage
from typing import Any

import httpx

from ..config import Settings

logger = logging.getLogger("kitchenhq-agent")


def _env(name: str) -> str:
    """An env var's trimmed value, treating an empty string the same as unset."""
    return (os.environ.get(name) or "").strip()


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _smtp_config() -> dict[str, Any] | None:
    """SMTP settings from the environment, or None when email is not configured."""
    host = _env("SMTP_HOST")
    if not host:
        return None
    username = _env("SMTP_USERNAME")
    use_ssl = _env_bool("SMTP_SSL", False)
    return {
        "host": host,
        "port": int(_env("SMTP_PORT") or ("465" if use_ssl else "587")),
        "username": username,
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "from_addr": _env("SMTP_FROM") or username or "kitchenhq@localhost",
        "use_ssl": use_ssl,
        "starttls": _env_bool("SMTP_STARTTLS", not use_ssl),
        "timeout": float(_env("SMTP_TIMEOUT") or "10"),
    }


def _split_addresses(raw: str) -> list[str]:
    """Parse a free-form address string (comma/semicolon/newline separated)."""
    parts = re.split(r"[,;\n]+", raw or "")
    return [part.strip() for part in parts if part.strip() and "@" in part]


def fetch_profile(settings: Settings) -> dict[str, Any]:
    """The household profile row from dbmcp's REST API; {} on any failure."""
    try:
        with httpx.Client(timeout=10) as client:
            response = client.get(
                f"{settings.db_api_url}/api/profile",
                headers={"X-API-Key": settings.kitchenhq_api_key},
            )
            response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        logger.warning("Could not read profile for email notification", exc_info=True)
        return {}


def _recipient(settings: Settings, *, respect_optout: bool = True) -> tuple[str, str, list[str]] | None:
    """(name, email, cc_emails) to notify, or None if unset / notifications disabled.

    ``notify_on_task_creation`` is the household's global "send me kitchen emails"
    switch; pass ``respect_optout=False`` only for a message the user always wants.
    """
    profile = fetch_profile(settings)
    email = (profile.get("email") or "").strip()
    if not email:
        return None
    if respect_optout and not profile.get("notify_on_task_creation", 1):
        return None
    cc = [addr for addr in _split_addresses(profile.get("cc_emails") or "") if addr.lower() != email.lower()]
    return (profile.get("name") or "").strip(), email, cc


def greeting(settings: Settings) -> str:
    recipient = _recipient(settings, respect_optout=False)
    return f"Hi {recipient[0] or 'there'}," if recipient else "Hi there,"


def send_email(
    subject: str,
    text_body: str,
    html_body: str | None = None,
    *,
    settings: Settings,
    respect_optout: bool = True,
) -> dict[str, Any]:
    """Send one email (plain text, plus an HTML alternative when given). Never raises.

    Returns ``{"sent": True, "to", "cc", "subject"}`` on success, or
    ``{"sent": False, "skipped": "<reason>"}`` when email is not configured, no
    recipient is set / notifications are off, or SMTP delivery failed.
    """
    config = _smtp_config()
    if config is None:
        return {"sent": False, "skipped": "SMTP is not configured (SMTP_HOST unset)"}
    recipient = _recipient(settings, respect_optout=respect_optout)
    if recipient is None:
        return {"sent": False, "skipped": "no profile email set or notifications disabled"}
    _name, email, cc = recipient

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config["from_addr"]
    message["To"] = email
    if cc:
        message["Cc"] = ", ".join(cc)
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    try:
        if config["use_ssl"]:
            with smtplib.SMTP_SSL(config["host"], config["port"], timeout=config["timeout"]) as server:
                _deliver(server, config, message)
        else:
            with smtplib.SMTP(config["host"], config["port"], timeout=config["timeout"]) as server:
                if config["starttls"]:
                    server.starttls()
                _deliver(server, config, message)
        logger.info("Email %r sent to %s", subject, email)
        return {"sent": True, "to": email, "cc": cc, "subject": subject}
    except Exception as error:  # noqa: BLE001 - a mail problem must not fail the caller's job
        logger.warning("Email %r to %s failed: %s", subject, email, error)
        return {"sent": False, "skipped": f"SMTP delivery failed: {error}"}


def _deliver(server: smtplib.SMTP, config: dict[str, Any], message: EmailMessage) -> None:
    if config["username"]:
        server.login(config["username"], config["password"])
    server.send_message(message)
