"""Bearer auth (team shared now, per-user later). Secrets redacted."""

from __future__ import annotations

import os

_TEAM_ENV = "MCP_BEARER_TEAM"
_TOKEN_ENV = "MCP_TOKEN"


def get_bearer() -> str | None:
    return os.environ.get(_TEAM_ENV) or os.environ.get(_TOKEN_ENV) or None


def is_authorized(presented: str | None) -> bool:
    expected = get_bearer()
    if not expected:
        return True  # local stdio without token
    return presented == expected


def redact(text: str) -> str:
    markers = ("Bearer ", "token=", "password=", "VIETSTOCK_COOKIE_LOGIN", "DNSE_SECRET")
    for marker in markers:
        if marker in text:
            return "[REDACTED]"
    return text
