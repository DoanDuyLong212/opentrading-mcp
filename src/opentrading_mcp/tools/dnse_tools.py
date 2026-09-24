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


def _project(rows: list[dict[str, Any]], columns: list[str] | None) -> list[dict[str, Any]]:
    if not columns:
        return rows
    return [{k: r[k] for k in columns if k in r} for r in rows]


def _summarize(symbol: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"symbol": symbol, "count": 0, "last": None, "high": None, "low": None}
    closes = [r.get("c", r.get("close")) for r in rows]
    highs = [r.get("h", r.get("high")) for r in rows]
    lows = [r.get("l", r.get("low")) for r in rows]
    last_close = closes[-1] if closes[-1] is not None else rows[-1]
    try:
        high = max(h for h in highs if isinstance(h, (int, float)))
    except ValueError:
        high = None
    try:
        low = min(lo for lo in lows if isinstance(lo, (int, float)))
    except ValueError:
        low = None
    return {"symbol": symbol, "count": len(rows), "last": last_close, "high": high, "low": low}


def register_dnse_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def dnse_ohlc_history(
        symbol: str = "VN30F1M",
        resolution: int = 15,
        bar_type: str = "derivative",
        from_date: str = "2018-08-01",
        summary: bool = False,
        columns: list[str] | None = None,
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Paginated futures/index bars via cursor. Use for VN30F1M backtest input."""
        if ctx is not None:
            await ctx.report_progress(0, 1, f"fetch {symbol}")
        try:
            rows = await run_blocking(
                functools.partial(
                    dnse_p.ohlc_history,
                    symbol=symbol,
                    bar_type=bar_type,
                    resolution=resolution,
                    from_date=from_date,
                ),
                "dnse_ohlc_history",
                timeout_secs=45.0,
            )
            if ctx is not None:
                await ctx.report_progress(1, 1, "done")
            if summary:
                return make_envelope(_summarize(symbol, rows), source="dnse-rest")
            return make_envelope(
                {"symbol": symbol, "bars": _project(rows, columns)}, source="dnse-rest"
            )
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
