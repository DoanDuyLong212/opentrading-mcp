"""Opencode-like MCP verify client.

Mirrors how opencode's client talks to an MCP server
(packages/opencode/src/mcp/index.ts + catalog.ts on the reference machine):
- transports: stdio subprocess, or remote StreamableHTTP with SSE fallback
- connect wrapped in timeout; failure closes the transport (no leaks)
- tools listed via tools/list, called via tools/call with per-call timeout
- tool key sanitized like opencode's toolName: /[^a-zA-Z0-9_-]/ -> _
- status states: connected | failed | needs_auth (auth reported, not fatal)

Used by tests/contract/test_verify_matrix.py and `opentrading-mcp verify`.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Any

from mcp.client.session import ClientSession
from mcp.shared.exceptions import McpError

DEFAULT_TIMEOUT = 30.0
SANITIZE_RE = re.compile(r"[^a-zA-Z0-9_-]")


def sanitize(name: str) -> str:
    return SANITIZE_RE.sub("_", name)


def tool_key(server: str, tool: str) -> str:
    return f"{sanitize(server)}_{sanitize(tool)}"


@dataclass
class CallResult:
    key: str
    ok: bool
    seconds: float
    detail: str = ""
    payload: Any = None


@dataclass
class VerifyClient:
    """A single MCP session emulating opencode's client behavior."""

    server_label: str
    timeout: float = DEFAULT_TIMEOUT

    def _stdio_stack(self, command: list[str]) -> Any:
        from mcp.client.stdio import StdioServerParameters, stdio_client

        params = StdioServerParameters(command=command[0], args=command[1:])
        return stdio_client(params)

    def _remote_stack(self, url: str) -> Any:
        from mcp.client.streamable_http import streamablehttp_client

        return streamablehttp_client(url, timeout=self.timeout)

    def _sse_stack(self, url: str) -> Any:
        from mcp.client.sse import sse_client

        return sse_client(url, timeout=self.timeout)

    async def run(
        self,
        calls: list[tuple[str, dict[str, Any], float]],
        transport: str,
        target: list[str] | str,
    ) -> list[CallResult]:
        """Connect, list tools, run calls. Returns one result per call."""
        done: dict[int, CallResult] = {}
        last_error = ""
        for stack in self._stacks(transport, target):
            missing = [(i, c) for i, c in enumerate(calls) if i not in done]
            if not missing:
                break
            try:
                async with stack as streams:
                    read, write = streams[0], streams[1]
                    async with ClientSession(read, write) as session:
                        await asyncio.wait_for(session.initialize(), timeout=self.timeout)
                        listed = await asyncio.wait_for(session.list_tools(), timeout=self.timeout)
                        available = {t.name for t in listed.tools}
                        for i, (name, args, call_timeout) in missing:
                            key = tool_key(self.server_label, name)
                            if name not in available:
                                done[i] = CallResult(key, False, 0.0, "tool not listed")
                                continue
                            started = time.monotonic()
                            try:
                                async with asyncio.timeout(call_timeout):
                                    raw = await session.call_tool(name, args)
                                done[i] = CallResult(key, True, time.monotonic() - started, "", raw)
                            except TimeoutError:
                                done[i] = CallResult(
                                    key,
                                    False,
                                    time.monotonic() - started,
                                    f"call timeout after {call_timeout}s",
                                )
                            except McpError as exc:
                                done[i] = CallResult(
                                    key, False, time.monotonic() - started, f"mcp error: {exc}"
                                )
                            except Exception as exc:
                                done[i] = CallResult(
                                    key,
                                    False,
                                    time.monotonic() - started,
                                    f"{type(exc).__name__}: {exc}",
                                )
            except Exception as exc:
                # Session-level failure (incl. close errors, which opencode
                # ignores too): keep completed calls, retry the rest.
                last_error = f"{type(exc).__name__}: {exc}"
                continue
        return [
            done.get(
                i,
                CallResult(
                    tool_key(self.server_label, calls[i][0]),
                    False,
                    0.0,
                    f"connect: {last_error}",
                ),
            )
            for i in range(len(calls))
        ]

    def _stacks(self, transport: str, target: list[str] | str) -> list[Any]:
        if transport == "stdio":
            assert isinstance(target, list)
            return [self._stdio_stack(target)]
        assert isinstance(target, str)
        return [self._remote_stack(target), self._sse_stack(target)]
