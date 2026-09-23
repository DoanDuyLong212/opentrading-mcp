"""Vietstock tools: auth, finance, company, industry, market flows, macro, news."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.providers import vietstock as vs_p
from opentrading_mcp.providers.errors import (
    ProviderAuthMissing,
    ProviderBadData,
    ProviderUnavailable,
)
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import READ_ONLY, AnyContext


def _na(tool: str, reason: str) -> dict[str, Any]:
    return make_envelope(
        {"tool": tool}, source="unavailable", warnings=[reason], availability="unavailable"
    )


def register_vs_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def vs_auth_status() -> dict[str, Any]:
        """Vietstock JWT state and expiry. Use before any paid BCTC call."""
        return make_envelope(vs_p.auth_status(), source="local")

    @server.tool(annotations=READ_ONLY)
    async def vs_financeinfo(
        symbol: str, period: str = "quarter", ctx: AnyContext | None = None
    ) -> dict[str, Any]:
        """Free-mirror statements, 12 quarters or years. Use when JWT is absent."""
        if ctx is not None:
            await ctx.log("info", f"vs_financeinfo {symbol} {period}")
        try:
            return make_envelope(vs_p.financeinfo(symbol, period), source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_financeinfo", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_market_price() -> dict[str, Any]:
        """Live board snapshot from Vietstock. Use as secondary quote source."""
        try:
            return make_envelope({"rows": vs_p.market_price()}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_market_price", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_market_index() -> dict[str, Any]:
        """Index closes with 1M and YTD change. Use for index context."""
        try:
            data = vs_p._post("/Data/GeneralMarket_GetMarketIndexVNData", {})
            return make_envelope({"indices": data}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_market_index", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_nn_flow() -> dict[str, Any]:
        """Foreign investor buy/sell chart. Use to cross-check DNSE WS flows."""
        try:
            data = vs_p._post("/data/KQGDGiaoDichNDTNNChart", {})
            return make_envelope({"flow": data}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_nn_flow", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_categories() -> dict[str, Any]:
        """Macro indicator catalogue (~60 categories). Use before indicator queries."""
        try:
            return make_envelope({"categories": vs_p.indicator_categories()}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_categories", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_indicator_data(category_id: int, term_type_id: int = 3) -> dict[str, Any]:
        """Macro series for a category and term type. Use for GDP, CPI, trade context."""
        try:
            data = vs_p._post(
                "/Macro/GetReportDataByIDs",
                {"termTypeID": term_type_id, "type": "CATEGORY", "listID": [category_id]},
            )
            return make_envelope({"category": category_id, "data": data}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_indicator_data", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_trading_info(symbol: str) -> dict[str, Any]:
        """Ceiling, floor, room, EPS, BVPS, PE, PB per symbol. Use for reference snapshot."""
        try:
            data = vs_p._post("/company/tradinginfo", {"code": symbol.upper(), "s": 0})
            return make_envelope({"symbol": symbol.upper(), "info": data}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_trading_info", str(exc))

    return [
        {"name": "vs_auth_status"},
        {"name": "vs_financeinfo"},
        {"name": "vs_market_price"},
        {"name": "vs_market_index"},
        {"name": "vs_nn_flow"},
        {"name": "vs_categories"},
        {"name": "vs_indicator_data"},
        {"name": "vs_trading_info"},
    ]
