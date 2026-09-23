"""Brief preset: morning briefs, news, calendars (compose only, no direct fetch)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import READ_ONLY


def register_brief_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def brief_build(scope: str = "vn") -> dict[str, Any]:
        """Compose morning brief from news, calendars and pins. Use at session start."""
        if scope not in ("vn", "world"):
            return make_envelope(
                {"tool": "brief_build"},
                source="local",
                warnings=[f"unknown scope {scope}"],
                availability="empty",
            )
        return make_envelope(
            {
                "scope": scope,
                "sections": ["overnight", "events", "calendar"],
                "sources": ["news_market", "economic_calendar", "corporate_calendar"],
            },
            source="composer",
        )

    @server.tool(annotations=READ_ONLY)
    async def news_market(limit: int = 10) -> dict[str, Any]:
        """Market news from official sources. Use for catalyst checks."""
        return make_envelope(
            {"items": [], "limit": limit, "note": "wire Fireant+RSS next"},
            source="stub",
            availability="empty",
        )

    @server.tool(annotations=READ_ONLY)
    async def news_symbol(symbol: str, limit: int = 10) -> dict[str, Any]:
        """Symbol news from official sources. Use to verify rumors."""
        return make_envelope(
            {"symbol": symbol.upper(), "items": [], "limit": limit},
            source="stub",
            availability="empty",
        )

    @server.tool(annotations=READ_ONLY)
    async def economic_calendar(scope: str = "vn") -> dict[str, Any]:
        """Event calendar per scope. Use for event-risk pricing."""
        return make_envelope({"scope": scope, "events": []}, source="stub", availability="empty")

    @server.tool(annotations=READ_ONLY)
    async def corporate_calendar(symbol: str | None = None) -> dict[str, Any]:
        """Dividend and meeting calendar. Use for income setups."""
        return make_envelope({"symbol": symbol, "events": []}, source="stub", availability="empty")

    return [
        {"name": "brief_build"},
        {"name": "news_market"},
        {"name": "news_symbol"},
        {"name": "economic_calendar"},
        {"name": "corporate_calendar"},
    ]
