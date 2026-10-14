"""DNSE extended tools: orderbook, foreign REST, indices, live futures, calendar."""

from __future__ import annotations

import functools
from datetime import date, timedelta
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.cache import TTL_SECONDS
from opentrading_mcp.providers import dnse as dnse_p
from opentrading_mcp.providers.errors import (
    ProviderAuthMissing,
    ProviderBadData,
    ProviderUnavailable,
)
from opentrading_mcp.tools.dnse_tools import _na
from opentrading_mcp.tools.shared import (
    READ_ONLY,
    cache_lookup,
    cache_store,
    price_ttl,
    run_blocking,
)


async def _call(tool: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
    return await run_blocking(functools.partial(fn, *args, **kwargs), tool, timeout_secs=45.0)


def register_dnse_ext_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def dnse_orderbook(symbol: str, depth: int = 3) -> dict[str, Any]:
        """Bid/ask depth. Use for microstructure reads.

        depth: levels per side (default 3). Equity symbols return live depth;
        VN30F1M futures book is usually empty upstream — use vn_trades tape.
        """
        fp = f"{symbol}|{depth}"
        hit = await cache_lookup("dnse_orderbook", fp)
        if hit is not None:
            return hit
        try:
            data = await _call("o", dnse_p.orderbook, symbol, depth)
            return await cache_store(
                "dnse_orderbook", fp, price_ttl(), data, source="dnse-rest"
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("dnse_orderbook", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def dnse_indices(symbols: list[str] | None = None) -> dict[str, Any]:
        """Index snapshots from WS cache. Use for live index reads.

        symbols: index channels to read (default VNINDEX+VN30).
        """
        fp = f"{symbols}"
        hit = await cache_lookup("dnse_indices", fp)
        if hit is not None:
            return hit
        try:
            data = dnse_p.ws_snapshot(symbols or ["VNINDEX", "VN30"])
            return await cache_store(
                "dnse_indices", fp, price_ttl(), data, source="dnse-ws"
            )
        except ProviderUnavailable as exc:
            return _na("dnse_indices", f"{exc} (fallback: vs_market_index)")

    @server.tool(annotations=READ_ONLY)
    async def dnse_vn30f1m_live(bars: int = 60) -> dict[str, Any]:
        """VN30F1M 1m bars aggregated to 15m with session remap. Use for intraday.

        bars: keep only the most recent N aggregated 15m bars.
        """
        fp = f"{bars}"
        hit = await cache_lookup("dnse_vn30f1m_live", fp)
        if hit is not None:
            return hit
        try:
            week_ago = (date.today() - timedelta(days=7)).isoformat()
            raw = await _call("l", dnse_p.ohlc_history, "VN30F1M", "derivative", 1, week_ago, 2000)
            raw_bars = raw if isinstance(raw, list) else []
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("dnse_vn30f1m_live", str(exc))
        def _num(value: Any) -> float | None:
            return value if isinstance(value, (int, float)) else None

        def _max(a: Any, b: Any) -> Any:
            return b if _num(a) is None else (a if _num(b) is None else max(a, b))

        def _min(a: Any, b: Any) -> Any:
            return b if _num(a) is None else (a if _num(b) is None else min(a, b))

        agg: dict[int, dict[str, Any]] = {}
        for bar in raw_bars:
            if not isinstance(bar, dict):
                continue
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
            slot["h"] = _max(slot["h"], bar.get("h", slot["h"]))
            slot["l"] = _min(slot["l"], bar.get("l", slot["l"]))
            slot["c"] = bar.get("c", slot["c"])
            slot["v"] = (slot["v"] or 0) + (bar.get("v") or 0)
        ordered = sorted(agg.values(), key=lambda b: b["t"])
        return await cache_store(
            "dnse_vn30f1m_live",
            fp,
            price_ttl(),
            {"symbol": "VN30F1M", "tf": "15m", "bars": ordered[-max(int(bars), 1) :]},
            source="dnse-rest",
            warnings=["14:30 remap applies in-session"],
        )

    @server.tool(annotations=READ_ONLY)
    async def dnse_working_dates(year: int | None = None) -> dict[str, Any]:
        """Lịch ngày giao dịch thực tế. Dùng khi lập kế hoạch phiên (ngày nào được giao dịch).

        Dùng khi: "thứ bảy có giao dịch không", "tháng này bao nhiêu phiên", kiểm tra ngày nghỉ lễ.
        Không dùng khi: giờ ATO/ATC/thanh toán T+ (dùng exchange_calendar — cơ chế tĩnh); lịch sự
            kiện doanh nghiệp (dùng event_calendar_vn).

        year: chỉ giữ ngày bắt đầu bằng năm này (ví dụ 2026). Là ngày giao dịch
        thật; exchange_calendar chứa cơ chế phiên tĩnh.
        """
        fp = f"{year}"
        hit = await cache_lookup("dnse_working_dates", fp)
        if hit is not None:
            return hit
        try:
            dates = await _call("w", dnse_p.working_dates)
            if year is not None and isinstance(dates, list):
                prefix = str(year)
                dates = [
                    d
                    for d in dates
                    if str(d.get("date", d) if isinstance(d, dict) else d).startswith(prefix)
                ]
            return await cache_store(
                "dnse_working_dates", fp, TTL_SECONDS["categories"],
                {"dates": dates}, source="dnse-rest",
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("dnse_working_dates", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def exchange_calendar() -> dict[str, Any]:
        """Giờ HOSE/HNX/UPCoM, ATO/ATC, thanh toán T+2. Dùng khi hỏi cơ chế phiên.

        Dùng khi: "ATO là gì", "mấy giờ đóng cửa", "tỷ lệ ký quỹ bao lâu mới nhận tiền".
        Không dùng khi: cần ngày giao dịch thật theo năm (dùng dnse_working_dates — dữ liệu động);
            trạng thái phiên hiện tại (dùng dnse_market_status). Dữ liệu tĩnh.
        """
        hit = await cache_lookup("exchange_calendar", "-")
        if hit is not None:
            return hit
        return await cache_store(
            "exchange_calendar",
            "-",
            TTL_SECONDS["categories"],
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
        {"name": "dnse_indices"},
        {"name": "dnse_vn30f1m_live"},
        {"name": "dnse_working_dates"},
        {"name": "exchange_calendar"},
    ]
