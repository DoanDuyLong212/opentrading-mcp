"""Brief preset: morning briefs, news, calendars wired to real sources."""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.providers import intel as intel_p
from opentrading_mcp.providers import vietstock as vs_p
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


def register_brief_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def brief_build(scope: str = "vn", date: str | None = None) -> dict[str, Any]:
        """Compose morning brief from news, odds and calendars. Use at session start."""
        if scope not in ("vn", "world"):
            return make_envelope(
                {"tool": "brief_build"},
                source="local",
                warnings=[f"unknown scope {scope}"],
                availability="empty",
            )
        sections: dict[str, Any] = {}
        try:
            sections["world_pins"] = await _call("p", intel_p.fear_greed, secs=30.0)
        except (ProviderUnavailable, ProviderBadData):
            sections["world_pins"] = None
        try:
            sections["news"] = await _call("n", vs_p.news_search, "thị trường chứng khoán", 10)
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData):
            try:
                sections["news"] = (
                    await _call("g", intel_p.gdelt_events, "vietnam stock market", secs=45.0)
                ).get("articles", [])
            except (ProviderUnavailable, ProviderBadData) as exc:
                sections["news"] = str(exc)
        try:
            cats = await _call("c", vs_p.indicator_categories)
            sections["macro_series_available"] = len(cats) if isinstance(cats, list) else 0
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData):
            sections["macro_series_available"] = 0
        data: dict[str, Any] = {
            "scope": scope,
            "sections": sections,
            "sources": ["vs_news_search", "gdelt", "alternative.me", "vs_categories"],
        }
        if date is not None:
            data["date"] = date
        return make_envelope(data, source="composer")

    @server.tool(annotations=READ_ONLY)
    async def news_market(limit: int = 10, sources: str | None = None) -> dict[str, Any]:
        """Market news: Vietstock first, GDELT fallback. Use for catalyst checks."""
        if sources == "gdelt":
            try:
                data = await _call("g", intel_p.gdelt_events, "vietnam market", limit)
                return make_envelope(data, source="gdelt")
            except (ProviderUnavailable, ProviderBadData) as exc:
                return _na("news_market", str(exc))
        try:
            data = await _call("n", vs_p.news_search, "thị trường chứng khoán", limit)
            return make_envelope({"articles": data}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData):
            try:
                data = await _call("g", intel_p.gdelt_events, "vietnam market", 20)
                return make_envelope(data, source="gdelt")
            except (ProviderUnavailable, ProviderBadData) as exc:
                return _na("news_market", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def news_symbol(
        symbol: str, limit: int = 10, sources: str | None = None
    ) -> dict[str, Any]:
        """Symbol news via Vietstock search. Use to verify rumors."""
        if sources == "gdelt":
            try:
                data = await _call("g", intel_p.gdelt_events, symbol.upper(), limit)
                return make_envelope(data, source="gdelt")
            except (ProviderUnavailable, ProviderBadData) as exc:
                return _na("news_symbol", str(exc))
        try:
            data = await _call("n", vs_p.news_search, symbol.upper(), limit)
            return make_envelope({"symbol": symbol.upper(), "articles": data}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("news_symbol", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def economic_calendar(scope: str = "vn", limit: int = 20) -> dict[str, Any]:
        """Macro series catalogue as event proxy. Use for data-availability checks."""
        if scope != "vn":
            return make_envelope(
                {"scope": scope},
                source="local",
                availability="empty",
                warnings=["world calendar: wire FRED releases next"],
            )
        try:
            cats = await _call("c", vs_p.indicator_categories)
            rows = [
                {
                    "category_id": c.get("CategoryID"),
                    "name": c.get("CategoryName"),
                    "has_data": c.get("HasData"),
                }
                for c in (cats if isinstance(cats, list) else [])
            ]
            return make_envelope(
                {"scope": scope, "series": rows[: max(int(limit), 1)]}, source="vietstock"
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("economic_calendar", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def corporate_calendar(symbol: str | None = None, limit: int = 20) -> dict[str, Any]:
        """Disclosures feed as corporate actions. Use for dividend/meeting scans."""
        try:
            docs = await _call("d", vs_p.documents, symbol or "VCB", 60)
            if isinstance(docs, list):
                docs = docs[: max(int(limit), 1)]
            return make_envelope(
                {"symbol": (symbol or "VCB").upper(), "docs": docs}, source="vietstock"
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("corporate_calendar", str(exc))

    return [
        {"name": "brief_build"},
        {"name": "news_market"},
        {"name": "news_symbol"},
        {"name": "economic_calendar"},
        {"name": "corporate_calendar"},
    ]
