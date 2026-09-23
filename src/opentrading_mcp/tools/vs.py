"""Vietstock tools: auth, finance, company, industry, market flows, macro, news."""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.providers import vietstock as vs_p
from opentrading_mcp.providers.errors import (
    ProviderAuthMissing,
    ProviderBadData,
    ProviderUnavailable,
)
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import READ_ONLY, AnyContext, run_blocking


def _na(tool: str, reason: str) -> dict[str, Any]:
    return make_envelope(
        {"tool": tool}, source="unavailable", warnings=[reason], availability="unavailable"
    )


async def _call(tool: str, fn: Any, *args: Any) -> Any:
    return await run_blocking(functools.partial(fn, *args), tool, timeout_secs=45.0)


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
            data = await _call("vs_financeinfo", vs_p.financeinfo, symbol, period)
            return make_envelope(data, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_financeinfo", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_market_price() -> dict[str, Any]:
        """Live board snapshot from Vietstock. Use as secondary quote source."""
        try:
            data = await _call("vs_market_price", vs_p.market_price)
            return make_envelope({"rows": data}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_market_price", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_market_index() -> dict[str, Any]:
        """Index closes with 1M and YTD change. Use for index context."""
        try:
            data = await _call(
                "vs_market_index", vs_p._post, "/Data/GeneralMarket_GetMarketIndexVNData", {}
            )
            return make_envelope({"indices": data}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_market_index", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_nn_flow() -> dict[str, Any]:
        """Foreign investor buy/sell chart. Use to cross-check DNSE WS flows."""
        try:
            data = await _call("vs_nn_flow", vs_p._post, "/data/KQGDGiaoDichNDTNNChart", {})
            return make_envelope({"flow": data}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na(
                "vs_nn_flow",
                f"{exc} (fallback: dnse_foreign_flow is the primary source)",
            )

    @server.tool(annotations=READ_ONLY)
    async def vs_categories() -> dict[str, Any]:
        """Macro indicator catalogue (~60 categories). Use before indicator queries."""
        try:
            data = await _call("vs_categories", vs_p.indicator_categories)
            return make_envelope({"categories": data}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_categories", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_indicator_data(category_id: int, term_type_id: int = 3) -> dict[str, Any]:
        """Macro series for a category and term type. Use for GDP, CPI, trade context."""
        try:
            data = await _call(
                "vs_indicator_data",
                vs_p._post,
                "/Macro/GetReportDataByIDs",
                {
                    "termTypeID": term_type_id,
                    "subTermTypeID": "",
                    "fromDate": "2021-06-30",
                    "toDate": "",
                    "type": "CATEGORY",
                    "listID[]": category_id,
                },
            )
            return make_envelope({"category": category_id, "data": data}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_indicator_data", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_trading_info(symbol: str) -> dict[str, Any]:
        """Ceiling, floor, room, EPS, BVPS, PE, PB per symbol. Use for reference snapshot."""
        try:
            data = await _call(
                "vs_trading_info",
                vs_p._post,
                "/company/tradinginfo",
                {"code": symbol.upper(), "s": 0},
            )
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
