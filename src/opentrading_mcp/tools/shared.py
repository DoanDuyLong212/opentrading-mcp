"""Shared tool annotation + context alias (imported by all tool modules)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True)
READ_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True)

AnyContext = Context[Any, Any, Any]
