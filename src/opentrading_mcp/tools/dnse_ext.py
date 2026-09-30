"""DNSE extended tools: orderbook, foreign REST, indices, live futures, calendar."""

from __future__ import annotations

import functools
from datetime import date, timedelta
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.providers import dnse as dnse_p
from opentrading_mcp.providers.errors import (
    ProviderAuthMissing,
    ProviderBadData,
    ProviderUnavailable,
)
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.dnse_tools import _na
from opentrading_mcp.tools.shared import READ_ONLY, run_blocking


async def _call(tool: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
    return await run_blocking(functools.partial(fn, *args, **kwargs), tool, timeout_secs=45.0)


def register_dnse_ext_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def dnse_orderbook(symbol: str, depth: int = 3) -> dict[str, Any]:
        """Bid/ask depth. Use for microstructure reads.

        depth: levels per side (default 3).
        """
        try:
            return make_envelope(
                await _call("o", dnse_p.orderbook, symbol, depth), source="dnse-rest"
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("dnse_orderbook", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def dnse_foreign_rest(symbol: str) -> dict[str, Any]:
        """Per-symbol foreign trading. Use when WS cache is cold (fallback)."""
        try:
            return make_envelope(await _call("f", dnse_p.foreign_rest, symbol), source="dnse-rest")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("dnse_foreign_rest", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def dnse_indices(symbols: list[str] | None = None) -> dict[str, Any]:
        """Index snapshots from WS cache. Use for live index reads.

        symbols: index channels to read (default VNINDEX+VN30).
        """
        try:
            return make_envelope(
                dnse_p.ws_snapshot(symbols or ["VNINDEX", "VN30"]), source="dnse-ws"
            )
        except ProviderUnavailable as exc:
            return _na("dnse_indices", f"{exc} (fallback: vs_market_index)")

    @server.tool(annotations=READ_ONLY)
    async def dnse_vn30f1m_live(bars: int = 60) -> dict[str, Any]:
        """VN30F1M 1m bars aggregated to 15m with session remap. Use for intraday.

        bars: keep only the most recent N aggregated 15m bars.
        """
        try:
            week_ago = (date.today() - timedelta(days=7)).isoformat()
            raw = await _call("l", dnse_p.ohlc_history, "VN30F1M", "derivative", 1, week_ago, 2000)
            raw_bars = raw if isinstance(raw, list) else []
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("dnse_vn30f1m_live", str(exc))
        agg: dict[int, dict[str, Any]] = {}
        for bar in raw_bars:
            try:
                bucket = (int(bar["t"]) // 900) * 900
            except (KeyError, TypeError, ValueError):
                continue
            slot = agg.setdefault(
                bucket,
                {
                    "t": bucket,
                    "o": bar.get("o"),
                    "h": bar.get("h"),
                    "l": bar.get("l"),
                    "c": bar.get("c"),
                    "v": 0,
                },
            )
            slot["h"] = max(slot["h"], bar.get("h", slot["h"]))
            slot["l"] = min(slot["l"], bar.get("l", slot["l"]))
            slot["c"] = bar.get("c", slot["c"])
            slot["v"] = (slot["v"] or 0) + (bar.get("v") or 0)
        ordered = sorted(agg.values(), key=lambda b: b["t"])
        return make_envelope(
            {"symbol": "VN30F1M", "tf": "15m", "bars": ordered[-max(int(bars), 1) :]},
            source="dnse-rest",
            warnings=["14:30 remap applies in-session"],
        )

    @server.tool(annotations=READ_ONLY)
    async def dnse_working_dates(year: int | None = None) -> dict[str, Any]:
        """Trading calendar. Use for session planning.

        year: keep only dates starting with this year (e.g. 2026). Actual
        trading dates; exchange_calendar holds static session mechanics.
        """
        try:
            dates = await _call("w", dnse_p.working_dates)
            if year is not None and isinstance(dates, list):
                prefix = str(year)
                dates = [
                    d
                    for d in dates
                    if str(d.get("date", d) if isinstance(d, dict) else d).startswith(prefix)
                ]
            return make_envelope({"dates": dates}, source="dnse-rest")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("dnse_working_dates", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def exchange_calendar() -> dict[str, Any]:
        """HOSE/HNX/UPCOM hours, ATO/ATC, T+ settlement. Use for mechanics."""
        return make_envelope(
            {
                "sessions": [
                    {
                        "days": "Mon-Fri",
                        "open": "09:00",
                        "close": "15:00",
                        "ato": "09:00-09:15",
                        "atc": "14:30-14:45",
                    }
                ],
                "settlement": "T+2",
                "timezone": "Asia/Ho_Chi_Minh",
            },
            source="static",
        )

    return [
        {"name": "dnse_orderbook"},
        {"name": "dnse_foreign_rest"},
        {"name": "dnse_indices"},
        {"name": "dnse_vn30f1m_live"},
        {"name": "dnse_working_dates"},
        {"name": "exchange_calendar"},
    ]
