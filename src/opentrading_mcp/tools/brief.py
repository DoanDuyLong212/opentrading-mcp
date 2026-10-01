"""Brief preset: morning briefs, news, calendars wired to real sources."""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.providers import intel as intel_p
from opentrading_mcp.providers import vietstock as vs_p
from opentrading_mcp.providers import vn_public as pub_p
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
    async def brief_build(
        scope: str = "vn", date: str | None = None, calendars: bool = False
    ) -> dict[str, Any]:
        """Compose morning brief from news, odds and calendars. Use at session start.

        scope: 'vn' or 'world'. date: ISO date the brief is for (recorded as-is).
        calendars: also attach IPO/macro/SBV sections (sbv_rates, macro_events_vn,
        ipo_calendar_vn); off by default to keep the brief fast.
        """
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
        if calendars:
            for key, fn in (
                ("sbv", pub_p.sbv_rates),
                ("macro_releases", pub_p.nso_releases),
                ("ipo", pub_p.hnx_auctions),
            ):
                try:
                    sections[key] = await _call(key, fn, secs=45.0)
                except (ProviderUnavailable, ProviderBadData) as exc:
                    sections[key] = str(exc)
        data: dict[str, Any] = {
            "scope": scope,
            "sections": sections,
            "sources": [
                "vietstock-dc (currently unavailable)",
                "gdelt",
                "alternative.me",
                "vs_categories",
            ],
        }
        if date is not None:
            data["date"] = date
        return make_envelope(data, source="composer")

    @server.tool(annotations=READ_ONLY)
    async def news_market(limit: int = 10, sources: str | None = None) -> dict[str, Any]:
        """Market news: Vietstock first, GDELT fallback. Use for catalyst checks.

        sources: 'gdelt' routes straight to GDELT (default tries Vietstock first).
        """
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
        """Symbol news via Vietstock search. Use to verify rumors.

        sources: 'gdelt' routes straight to GDELT. Default tries Vietstock dc
        first, falls back to GDELT when the dc route is down (P14 — it is
        currently down, so expect the GDELT leg to serve).
        """
        if sources == "gdelt":
            try:
                data = await _call("g", intel_p.gdelt_events, symbol.upper(), limit)
                return make_envelope(data, source="gdelt")
            except (ProviderUnavailable, ProviderBadData) as exc:
                return _na("news_symbol", str(exc))
        try:
            data = await _call("n", vs_p.news_search, symbol.upper(), limit)
            return make_envelope({"symbol": symbol.upper(), "articles": data}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData):
            try:
                data = await _call(
                    "g", intel_p.gdelt_events, f"{symbol.upper()} stock", 20, secs=45.0
                )
                return make_envelope(data, source="gdelt")
            except (ProviderUnavailable, ProviderBadData) as exc:
                return _na("news_symbol", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def economic_calendar(scope: str = "vn", limit: int = 20) -> dict[str, Any]:
        """Macro series catalogue as event proxy. Use for data-availability checks.

        scope: 'vn' only (others return empty with a warning). limit: max series.
        Not a real calendar; for trading dates use dnse_working_dates instead.
        """
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
    async def sbv_rates() -> dict[str, Any]:
        """SBV policy and interbank rates, scraped static page. Use for rate regime.

        Values change rarely; upstream has no API.
        """
        try:
            return make_envelope(await _call("s", pub_p.sbv_rates), source="sbv-scrape")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("sbv_rates", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def macro_events_vn() -> dict[str, Any]:
        """NSO release listings with reference and next dates. Use for data calendar.

        Covers CPI schedule and releases; full year schedule lives in an NSO PDF.
        """
        try:
            return make_envelope(
                {"releases": await _call("m", pub_p.nso_releases)}, source="nso-scrape"
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("macro_events_vn", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def corporate_calendar(symbol: str | None = None, limit: int = 20) -> dict[str, Any]:
        """Disclosures feed as corporate actions. Use for dividend/meeting scans.

        symbol: omit for VN overview; limit: max disclosures. Raw feed;
        company_events classifies the same disclosures into kinds.
        """
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
        {"name": "sbv_rates"},
        {"name": "macro_events_vn"},
    ]
