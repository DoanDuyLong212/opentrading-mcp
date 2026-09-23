"""DNSE tools: futures history, live trades, foreign flows, calendar."""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.providers import dnse as dnse_p
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


def register_dnse_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def dnse_ohlc_history(
        symbol: str = "VN30F1M", resolution: int = 15, ctx: AnyContext | None = None
    ) -> dict[str, Any]:
        """Paginated futures/index bars via cursor. Use for VN30F1M backtest input."""
        if ctx is not None:
            await ctx.report_progress(0, 1, f"fetch {symbol}")
        try:
            rows = await run_blocking(
                functools.partial(dnse_p.ohlc_history, symbol=symbol, resolution=resolution),
                "dnse_ohlc_history",
                timeout_secs=45.0,
            )
            if ctx is not None:
                await ctx.report_progress(1, 1, "done")
            return make_envelope({"symbol": symbol, "bars": rows}, source="dnse-rest")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("dnse_ohlc_history", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def dnse_latest_trade(symbols: list[str]) -> dict[str, Any]:
        """Latest match price and totals per symbol. Use for realtime fallback."""
        try:
            data = await run_blocking(
                functools.partial(dnse_p.latest_trade, symbols),
                "dnse_latest_trade",
                timeout_secs=45.0,
            )
            return make_envelope({"trades": data}, source="dnse-rest")
        except (ProviderAuthMissing, ProviderUnavailable) as exc:
            return _na("dnse_latest_trade", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def dnse_foreign_flow() -> dict[str, Any]:
        """Net foreign flow from WS cache. Use as primary smart-money read."""
        try:
            return make_envelope(dnse_p.ws_snapshot(["VNINDEX"]), source="dnse-ws")
        except ProviderUnavailable as exc:
            return _na("dnse_foreign_flow", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def dnse_ws_snapshot(symbols: list[str] | None = None) -> dict[str, Any]:
        """Raw worker snapshot for symbols. Use to debug realtime staleness."""
        try:
            return make_envelope(
                dnse_p.ws_snapshot(symbols or ["VN30F1M", "VNINDEX", "VN30"]),
                source="dnse-ws",
            )
        except ProviderUnavailable as exc:
            return _na("dnse_ws_snapshot", str(exc))

    return [
        {"name": "dnse_ohlc_history"},
        {"name": "dnse_latest_trade"},
        {"name": "dnse_foreign_flow"},
        {"name": "dnse_ws_snapshot"},
    ]
