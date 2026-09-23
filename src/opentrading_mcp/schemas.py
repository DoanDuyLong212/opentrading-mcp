"""Shared envelope + typed error contract.

Every tool returns an envelope so opencode/Claude/Cursor can render
provenance without parsing free text. Failures use stable ErrorCode
strings compatible with OpenTrading errors.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

TIMEZONE = "Asia/Ho_Chi_Minh"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def make_envelope(
    data: Any,
    source: str,
    warnings: list[str] | None = None,
    availability: str | None = None,
) -> dict[str, Any]:
    has_data = data not in (None, {}, [], ())
    return {
        "data": data,
        "provenance": {
            "source": source,
            "as_of": utc_now_iso(),
            "timezone": TIMEZONE,
        },
        "warnings": warnings or [],
        "availability": availability or ("available" if has_data else "empty"),
    }


def mcp_tool_error(code: str, message: str, retryable: bool = False) -> dict[str, Any]:
    return {"code": code, "message": message[:2000], "retryable": retryable}
