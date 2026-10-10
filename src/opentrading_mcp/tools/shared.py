"""Shared tool annotation + context alias (imported by all tool modules)."""

from __future__ import annotations

import asyncio
import contextvars
import functools
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
READ_WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
# Phân loại write để client (OpenTrading RwLock, Claude permission, Cursor review)
# quyết định chạy song song vs hỏi duyệt:
READ_WRITE_CREATE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
READ_WRITE_DELETE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False
)
READ_WRITE_STATE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
# Tools gọi mạng ngoài (web/yfinance/Binance/GDELT/Polymarket/FRED): open-world.
READ_ONLY_OPEN = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
)

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


def blocking_slots() -> int:
    """How many blocking upstream calls may run at once (env MCP_BLOCKING_SLOTS, default 2).

    vnstock/pandas work is CPU-bound and holds the GIL. On a 0.1-CPU host (Render free)
    five of them at once starved the event loop until /healthz timed out and the
    instance was killed (10/10/2026). Extra calls wait for a slot instead.
    """
    try:
        return max(1, int(os.environ.get("MCP_BLOCKING_SLOTS", "2")))
    except ValueError:
        return 2


# Blocking upstream work runs here, not in asyncio's default pool: a queued call holds no
# thread, so Redis reads (to_thread) and /readyz never wait behind a burst of tool calls.
_EXECUTOR = ThreadPoolExecutor(max_workers=blocking_slots(), thread_name_prefix="upstream")


async def run_blocking[T](fn: Callable[[], T], tool: str, timeout_secs: float = 60.0) -> T:
    """Run a blocking upstream call in a worker thread with a hard timeout.

    Prevents one stalled upstream (e.g. retail endpoints from certain
    regions) from hanging the tool past the client's call timeout.

    At most ``blocking_slots()`` calls run at once; the rest queue. Queue time counts
    toward ``timeout_secs``. On a timeout a call that has not started is cancelled and
    never runs; one that is running keeps its worker until it really ends (threads
    cannot be killed), so the cap holds even for stalled upstreams.
    """
    from opentrading_mcp.providers.errors import ProviderUnavailable

    loop = asyncio.get_running_loop()
    ctx = contextvars.copy_context()
    future = loop.run_in_executor(_EXECUTOR, functools.partial(ctx.run, fn))
    try:
        return await asyncio.wait_for(future, timeout_secs)
    except TimeoutError as exc:
        raise ProviderUnavailable(f"{tool} timed out after {timeout_secs}s") from exc
