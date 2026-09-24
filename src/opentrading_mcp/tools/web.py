"""Web preset: generic fetch + delegated search (mirror opencode webfetch/websearch)."""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.providers import webfetch as fetch_p
from opentrading_mcp.providers import websearch as search_p
from opentrading_mcp.providers.errors import (
    ProviderAuthMissing,
    ProviderBadData,
    ProviderUnavailable,
)
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import READ_ONLY, run_blocking


def _na(tool: str, reason: str) -> dict[str, Any]:
    return make_envelope(
        {"tool": tool}, source="unavailable", warnings=[reason], availability="unavailable"
    )


async def _call(tool: str, fn: Any, *args: Any, secs: float = 45.0) -> Any:
    return await run_blocking(functools.partial(fn, *args), tool, timeout_secs=secs)


def register_web_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def web_fetch(
        url: str, format: str = "markdown", timeout_seconds: int = 30
    ) -> dict[str, Any]:
        """Fetch a URL and convert to markdown, text or html. Use for reading web content."""
        try:
            data = await _call(
                "web_fetch",
                fetch_p.fetch_url,
                url,
                format,
                min(timeout_seconds, 120),
                secs=120.0,
            )
            return make_envelope(data, source="web")
        except (ProviderBadData, ProviderUnavailable) as exc:
            return _na("web_fetch", str(exc))

    registered = [{"name": "web_fetch"}]

    if search_p.web_search_available():
        # Mirror opencode registry gating: websearch is hidden when no provider key exists.

        @server.tool(annotations=READ_ONLY)
        async def web_search(
            query: str,
            num_results: int = 8,
            livecrawl: str = "fallback",
            search_type: str = "auto",
        ) -> dict[str, Any]:
            """Search the web via Exa/Parallel providers. Use for up-to-date information."""
            try:
                data = await _call(
                    "web_search",
                    search_p.search,
                    query,
                    num_results,
                    livecrawl,
                    search_type,
                    secs=60.0,
                )
                return make_envelope(data, source=data.get("provider", "web"))
            except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
                return _na("web_search", str(exc))

        registered.append({"name": "web_search"})

    return registered
