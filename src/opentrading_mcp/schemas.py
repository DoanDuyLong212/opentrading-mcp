"""Shared envelope + typed error contract.

Every tool returns an envelope so opencode/Claude/Cursor can render
provenance without parsing free text. Failures use stable ErrorCode
strings compatible with OpenTrading errors.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

TIMEZONE = "Asia/Ho_Chi_Minh"
_TZ = ZoneInfo(TIMEZONE)

# Controlled provenance vocabulary (mcp-builder: machine-readable source).
ALLOWED_SOURCES = frozenset(
    {
        "vietstock",
        "vnstock",
        "dnse-rest",
        "dnse-ws",
        "yfinance",
        "binance-spot",
        "binance-futures",
        "fred",
        "worldbank",
        "gdelt",
        "fireant",
        "polymarket",
        "web",
        "web-search",
        "local",
        "file",
        "postgres",
        "cache",
        "cache-stale",
        "computed-local",
        "computed-yfinance",
        "composer",
        "unavailable",
        "static",
        "alternative.me",
        "msn",
        "btmc-direct",
        "vnstock-retail",
    }
)

# Legacy aliases coerced to canonical sources (no behavior change otherwise).
_SOURCE_ALIASES = {
    "v": "vietstock",
    "vnstock+dnse": "computed-local",
    "fireant+groq": "fireant",
    "sbv-scrape": "web",
}


def utc_now_iso() -> str:
    return datetime.now(_TZ).isoformat()


def make_envelope(
    data: Any,
    source: str,
    warnings: list[str] | None = None,
    availability: str | None = None,
    page: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = _SOURCE_ALIASES.get(source, source)
    has_data = data not in (None, {}, [], ())
    body: dict[str, Any] = {
        "data": data,
        "provenance": {
            "source": source,
            "as_of": utc_now_iso(),
            "timezone": TIMEZONE,
        },
        "warnings": warnings or [],
        "availability": availability or ("available" if has_data else "empty"),
    }
    if page is not None:
        body["page"] = page
    if error is not None:
        body["error"] = error
    return body


def paginate_list(
    rows: list[Any], limit: int, offset: int = 0
) -> tuple[list[Any], dict[str, Any]]:
    """Cắt list + trả page{total,offset,limit,next} chuẩn cho mọi tool list."""
    total = len(rows)
    limit = max(int(limit), 1)
    offset = max(int(offset), 0)
    items = rows[offset : offset + limit]
    nxt = offset + limit if offset + limit < total else None
    return items, {"total": total, "offset": offset, "limit": limit, "next": nxt}


def mcp_tool_error(code: str, message: str, retryable: bool = False) -> dict[str, Any]:
    return {"code": code, "message": message[:2000], "retryable": retryable}
