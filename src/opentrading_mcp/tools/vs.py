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
        """Free-mirror statements, 12 quarters or years. Use when JWT is absent.

        period: 'quarter' (12 quarters) or 'year' (annual).
        """
        if ctx is not None:
            await ctx.log("info", f"vs_financeinfo {symbol} {period}")
        try:
            data = await _call("vs_financeinfo", vs_p.financeinfo, symbol, period)
            return make_envelope(data, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_financeinfo", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_market_price(type: int = 2) -> dict[str, Any]:
        """Live board snapshot from Vietstock. Use as secondary quote source.

        type: board id (2 = main board).
        """
        try:
            data = await _call("vs_market_price", vs_p.market_price, type)
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
    async def vs_nn_flow(days: int = 90) -> dict[str, Any]:
        """Foreign investor buy/sell chart. Use to cross-check DNSE WS flows.

        days: keep only the most recent N chart points.
        """
        try:
            data = await _call("vs_nn_flow", vs_p.nn_flow_chart)
            if isinstance(data, list) and len(data) == 2 and all(isinstance(p, list) for p in data):
                tail = max(int(days), 1)
                data = [data[0][-tail:], data[1][-tail:]]
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
    async def vs_indicator_data(
        category_id: int,
        term_type_id: int = 3,
        sub_term_type_id: str | None = None,
        from_date: str = "2022-01-01",
        to_date: str | None = None,
    ) -> dict[str, Any]:
        """Macro series (GDP/CPI/FX/trade) via browser-session replay. Use for macro reads.

        term_type_id: 1 daily, 2 monthly, 3 quarterly, 4 yearly, 5 YTD, 6 MoM,
        7 YoY, 8 QoQ — pairs must match each category's ListTermType metadata
        (e.g. GDP 73 tt=3, CPI 15 tt=7 sub=2). from_date default 2022-01-01.
        Uses the full browser cookie jar (HAR/env seed); Standard pack serves it.
        Rows: {name, group, period, year, value, unit, timeorder}.
        """
        try:
            out = await _call(
                "vs_indicator_data",
                vs_p.macro_report_data,
                term_type_id,
                category_id,
                sub_term_type_id or "",
                from_date,
                to_date,
            )
            rows = out.get("rows", []) if isinstance(out, dict) else []
            availability = "available" if rows else "empty"
            return make_envelope(out, source="vietstock", availability=availability)
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
