"""Web: generic fetch + delegated search (mirror opencode webfetch/websearch)."""

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
from opentrading_mcp.tools.shared import READ_ONLY_OPEN, run_blocking


def _na(tool: str, reason: str) -> dict[str, Any]:
    return make_envelope(
        {"tool": tool}, source="unavailable", warnings=[reason], availability="unavailable"
    )


async def _call(tool: str, fn: Any, *args: Any, secs: float = 45.0) -> Any:
    return await run_blocking(functools.partial(fn, *args), tool, timeout_secs=secs)


def register_web_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY_OPEN)
    async def web_fetch(
        url: str, format: str = "markdown", timeout_seconds: int = 30
    ) -> dict[str, Any]:
        """Fetch a URL and convert to markdown, text, html or pdf-text. Use for reading web content.

        format: 'markdown' (default), 'text', 'html' or 'pdf' (PDF text extraction,
        best-effort stdlib-only; scanned PDFs report honestly). timeout_seconds: max
        fetch time (default 30).
        """
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

        @server.tool(annotations=READ_ONLY_OPEN)
        async def web_search(
            query: str,
            num_results: int = 8,
            livecrawl: str = "fallback",
            search_type: str = "auto",
            context_max_chars: int | None = None,
        ) -> dict[str, Any]:
            """Search the web via Exa/Parallel providers. Use for up-to-date information.

            num_results: results requested (default 8). livecrawl: 'fallback' uses
            cached index first, 'preferred' crawls live. search_type: 'auto' (default),
            'fast', or 'deep'. context_max_chars: cap on returned context.
            """
            try:
                data = await _call(
                    "web_search",
                    search_p.search,
                    query,
                    num_results,
                    livecrawl,
                    search_type,
                    context_max_chars,
                    secs=60.0,
                )
                provider = data.get("provider", "web") if isinstance(data, dict) else "web"
                return make_envelope(
                    data,
                    source="web-search",
                    warnings=[f"provider={provider}"] if provider != "web" else None,
                )
            except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
                return _na("web_search", str(exc))

        registered.append({"name": "web_search"})

    return registered
