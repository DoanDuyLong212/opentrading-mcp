"""Shared envelope + typed error contract.

Every tool returns an envelope so opencode/Claude/Cursor can render
provenance without parsing free text. Failures use stable ErrorCode
strings compatible with OpenTrading errors.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

TIMEZONE = "Asia/Ho_Chi_Minh"
# Vietnam has no DST; a fixed offset avoids needing tzdata on Windows.
VN_TZ = timezone(timedelta(hours=7), TIMEZONE)


def now_iso() -> str:
    """Current time in Vietnam, ISO 8601 with +07:00 (matches provenance.timezone)."""
    return datetime.now(VN_TZ).isoformat(timespec="seconds")


def make_envelope(
    data: Any,
    source: str,
    warnings: list[str] | None = None,
    availability: str | None = None,
    data_as_of: str | None = None,
) -> dict[str, Any]:
    """Wrap a result. ``as_of`` is when this envelope was built; ``data_as_of``
    (optional) is when the data itself was fetched, e.g. for cache hits."""
    has_data = data not in (None, {}, [], ())
    provenance: dict[str, Any] = {"source": source, "as_of": now_iso(), "timezone": TIMEZONE}
    if data_as_of:
        provenance["data_as_of"] = data_as_of
    return {
        "data": data,
        "provenance": provenance,
        "warnings": warnings or [],
        "availability": availability or ("available" if has_data else "empty"),
    }


def mcp_tool_error(code: str, message: str, retryable: bool = False) -> dict[str, Any]:
    return {"code": code, "message": message[:2000], "retryable": retryable}
