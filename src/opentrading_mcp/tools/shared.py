"""Shared tool annotation + context alias (imported by all tool modules)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True)
READ_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True)
# Plain INSERTs: calling twice creates two rows (or fails on the unique name).
WRITE_NOT_IDEMPOTENT = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False
)
# Removes stored data; clients should confirm before running these.
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True)

# Write tools whose effect READ_WRITE misdescribes; applied by OpenTradingMCP.tool().
ANNOTATION_OVERRIDES: dict[str, ToolAnnotations] = {
    "watchlist_create": WRITE_NOT_IDEMPOTENT,
    "alert_create": WRITE_NOT_IDEMPOTENT,
    "watchlist_delete": DESTRUCTIVE,
    "watchlist_remove": DESTRUCTIVE,
    "alert_delete": DESTRUCTIVE,
}

AnyContext = Context[Any, Any, Any]


CLOSE_KEYS = ("c", "close", "Close", "CLOSE")
HIGH_KEYS = ("h", "high", "High", "HIGH")
LOW_KEYS = ("l", "low", "Low", "LOW")


def pick_value(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """Return the first matching key's value, or None (P1 shared helper)."""
    for k in keys:
        if k in row:
            return row[k]
    return None


def project_rows(rows: list[dict[str, Any]], columns: list[str] | None) -> list[dict[str, Any]]:
    """Project rows to a column subset; None/empty returns rows as-is (P1 shared)."""
    if not columns:
        return rows
    return [{k: r[k] for k in columns if k in r} for r in rows]


def summarize_rows(
    symbol: str, rows: list[dict[str, Any]], *, uppercase: bool = True
) -> dict[str, Any]:
    """Summarize OHLC rows to {symbol, count, last, high, low} (P1 shared).

    uppercase=True preserves vn.py/vn_ext.py behavior (symbol.upper());
    uppercase=False preserves market.py/dnse_tools.py behavior (symbol as-is).
    Key aliases cover c/close/Close/CLOSE etc (superset of dnse's old subset).
    """
    name = symbol.upper() if uppercase else symbol
    if not rows:
        return {"symbol": name, "count": 0, "last": None, "high": None, "low": None}
    closes = [pick_value(r, CLOSE_KEYS) for r in rows]
    highs = [pick_value(r, HIGH_KEYS) for r in rows]
    lows = [pick_value(r, LOW_KEYS) for r in rows]
    last_close = closes[-1] if closes[-1] is not None else rows[-1]
    try:
        high = max(h for h in highs if isinstance(h, (int, float)))
    except ValueError:
        high = None
    try:
        low = min(lo for lo in lows if isinstance(lo, (int, float)))
    except ValueError:
        low = None
    return {
        "symbol": name,
        "count": len(rows),
        "last": last_close,
        "high": high,
        "low": low,
    }


async def run_blocking[T](fn: Callable[[], T], tool: str, timeout_secs: float = 60.0) -> T:
    """Run a blocking upstream call in a thread with a hard timeout.

    Prevents one stalled upstream (e.g. retail endpoints from certain
    regions) from hanging the tool past the client's call timeout.
    """
    from opentrading_mcp.providers.errors import ProviderUnavailable

    try:
        return await asyncio.wait_for(asyncio.to_thread(fn), timeout_secs)
    except TimeoutError as exc:
        raise ProviderUnavailable(f"{tool} timed out after {timeout_secs}s") from exc
