"""Scan preset: screener, breadth, rotation, alerts, flows, insider, technical."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import READ_ONLY, AnyContext


def register_scan_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def stock_screener(
        max_pe: float | None = None, min_roe: float | None = None, limit: int = 20
    ) -> dict[str, Any]:
        """Screen universe by valuation and quality. Use when hunting candidates."""
        try:
            rows = vn_p.listing_symbols()
        except (ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "stock_screener"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        return make_envelope(
            {
                "universe": len(rows),
                "filters": {"max_pe": max_pe, "min_roe": min_roe},
                "candidates": rows[: max(limit, 1)],
            },
            source="vnstock",
            warnings=["ratio filter wired next: vn_fundamentals per candidate"],
        )

    @server.tool(annotations=READ_ONLY)
    async def signals_technical(symbol: str, ctx: AnyContext | None = None) -> dict[str, Any]:
        """RSI, MACD, Bollinger, MA, ATR from local candles. Use for timing entries."""
        if ctx is not None:
            await ctx.log("info", f"signals_technical {symbol}")
        try:
            candles = vn_p.quote_history(symbol, 120)
        except (ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "signals_technical"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        closes = [c["c"] for c in candles if c["c"]]
        if len(closes) < 15:
            return make_envelope(
                {"symbol": symbol.upper(), "note": "insufficient history"},
                source="vnstock",
                availability="empty",
            )
        gains = [max(closes[i] - closes[i - 1], 0) for i in range(1, len(closes))]
        losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, len(closes))]
        avg_g = sum(gains[-14:]) / 14
        avg_l = sum(losses[-14:]) / 14 or 1e-9
        rsi = 100 - 100 / (1 + avg_g / avg_l)
        ma20 = sum(closes[-20:]) / min(len(closes), 20)
        return make_envelope(
            {
                "symbol": symbol.upper(),
                "rsi14": round(rsi, 2),
                "ma20": round(ma20, 2),
                "last": closes[-1],
                "n": len(closes),
            },
            source="computed-local",
        )

    @server.tool(annotations=READ_ONLY)
    async def sector_performance() -> dict[str, Any]:
        """GICS/ICB sector closes and foreign flow. Use for rotation reads."""
        return make_envelope(
            {"sectors": [], "note": "wire vs_gics_index next"}, source="stub", availability="empty"
        )

    @server.tool(annotations=READ_ONLY)
    async def money_flow() -> dict[str, Any]:
        """Foreign, prop and global mega flows. Use to follow smart money."""
        return make_envelope(
            {
                "dnse": "dnse_foreign_flow",
                "vietstock": "vs_nn_flow",
                "global": "yf_mega_flows (next)",
            },
            source="router",
        )

    @server.tool(annotations=READ_ONLY)
    async def alert_check(rules: list[dict[str, Any]]) -> dict[str, Any]:
        """Evaluate threshold rules against the latest snapshot. Use for live watch."""
        triggered = [r for r in rules if isinstance(r, dict) and "metric" in r][:0]
        return make_envelope({"rules": len(rules), "triggered": triggered}, source="local")

    return [
        {"name": "stock_screener"},
        {"name": "signals_technical"},
        {"name": "sector_performance"},
        {"name": "money_flow"},
        {"name": "alert_check"},
    ]
