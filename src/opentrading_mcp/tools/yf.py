"""yfinance tools: global indices, commodities, yield curve, world breadth."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.providers import yfinance as yf_p
from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import READ_ONLY, AnyContext


def _na(tool: str, reason: str) -> dict[str, Any]:
    return make_envelope(
        {"tool": tool}, source="unavailable", warnings=[reason], availability="unavailable"
    )


def register_yf_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def yf_global_indices(ctx: AnyContext | None = None) -> dict[str, Any]:
        """9 global benchmarks, 2d daily. Use for overnight context."""
        if ctx is not None:
            await ctx.report_progress(0, 1, "fetch global")
        try:
            return make_envelope({"indices": yf_p.batch_last(yf_p.GLOBAL_9)}, source="yfinance")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("yf_global_indices", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def yf_commodities() -> dict[str, Any]:
        """Gold, oil, metals, BTC, VND and dollar index. Use for input-cost context."""
        try:
            return make_envelope({"items": yf_p.batch_last(yf_p.COMMO_13)}, source="yfinance")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("yf_commodities", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def yf_yield_curve() -> dict[str, Any]:
        """US 2Y/10Y and inversion flag. Use for rates and regime context."""
        try:
            return make_envelope(yf_p.yield_curve(), source="yfinance")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("yf_yield_curve", str(exc))

    return [
        {"name": "yf_global_indices"},
        {"name": "yf_commodities"},
        {"name": "yf_yield_curve"},
    ]
