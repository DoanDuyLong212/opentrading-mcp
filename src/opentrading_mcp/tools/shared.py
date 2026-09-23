"""Shared tool annotation + context alias (imported by all tool modules)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True)
READ_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True)

AnyContext = Context[Any, Any, Any]


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
