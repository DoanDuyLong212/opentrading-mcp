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


# Named indicators → (category_id, term_type_id, sub_term_type_id). A wrong pair returns
# empty rows, so the common series are resolved here instead of by the model.
MACRO_INDICATORS: dict[str, tuple[int, int, str | None]] = {
    "GDP": (73, 3, None),  # quarterly
    "CPI": (15, 7, "2"),  # year on year
    "XK": (38, 2, None),  # exports, monthly
}
MACRO_INDICATOR_ALIASES = {"EXPORT": "XK", "EXPORTS": "XK"}


async def _call(tool: str, fn: Any, *args: Any) -> Any:
    return await run_blocking(functools.partial(fn, *args), tool, timeout_secs=45.0)


def _coerce_id(value: Any, field: str) -> int:
    """Accept numeric strings from models ("3", '"3"' → 3); raise BadData otherwise."""
    if isinstance(value, bool):
        raise ProviderBadData(f"{field} must be an integer id, got boolean")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        s = value.strip().strip('"').strip("'").strip()
        if s.lstrip("-").isdigit():
            return int(s)
    raise ProviderBadData(
        f"{field} must be an integer id (e.g. 3), got {value!r}"
    )


def _coerce_sub(value: Any) -> str:
    """Normalize sub id: None → "", int → str, strip stray quotes."""
    if value is None:
        return ""
    return str(value).strip().strip('"').strip("'").strip()


def register_vs_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def vs_auth_status() -> dict[str, Any]:
        """Vietstock JWT state and expiry. Use before any paid BCTC call."""
        return make_envelope(vs_p.auth_status(), source="local")

    @server.tool(annotations=READ_ONLY)
    async def vs_financeinfo(
        symbol: str, period: str = "quarter", ctx: AnyContext | None = None
    ) -> dict[str, Any]:
        """BCTC mirror miễn phí, 12 quý hoặc năm. Dùng khi KHÔNG có JWT Vietstock.

        Dùng khi: đọc BCTC mà chưa đăng nhập Vietstock.
        Không dùng khi: đã có JWT (dùng financial_detail — đầy đủ từng dòng); chỉ cần đọc nhanh gọn
            (dùng financial_statements — cùng nguồn mirror, gọn hơn).

        period: 'quarter' (12 quý) hoặc 'year' (năm).
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
        """Biểu đồ mua/bán khối ngoại. Dùng khi đối chiếu chéo dòng tiền với DNSE WS.

        Dùng khi: kiểm tra lại số liệu money_flow/dnse_foreign_flow bằng nguồn thứ hai.
        Không dùng khi: cần đọc smart-money chính trong phiên (dùng money_flow trước; tool này là
            nguồn đối chiếu, days mặc định 90 điểm).

        days: chỉ giữ N điểm biểu đồ gần nhất.
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
        category_id: int | None = None,
        term_type_id: int | str = 3,
        sub_term_type_id: str | int | None = None,
        from_date: str = "2022-01-01",
        to_date: str | None = None,
        indicator: str | None = None,
    ) -> dict[str, Any]:
        """Macro series (GDP/CPI/FX/trade) via browser-session replay. Use for macro reads.

        indicator: 'GDP' (quarterly), 'CPI' (YoY) or 'XK' (exports, monthly) — the
        server fills the id pair, so prefer it for these. Other series: pass
        category_id from vs_categories plus term_type_id: 1 daily, 2 monthly,
        3 quarterly, 4 yearly, 5 YTD, 6 MoM, 7 YoY, 8 QoQ — pairs must match each
        category's ListTermType metadata or rows come back empty.
        from_date default 2022-01-01. Uses the full browser cookie jar (HAR/env
        seed); Standard pack serves it.
        Rows: {name, group, period, year, value, unit, timeorder}.
        Example: {"indicator": "CPI"}; {"category_id": 76, "term_type_id": 2}.
        Numbers accepted as strings and coerced (e.g. "3" → 3).
        """
        warnings: list[str] = []
        if indicator:
            key = indicator.strip().upper()
            key = MACRO_INDICATOR_ALIASES.get(key, key)
            if key not in MACRO_INDICATORS:
                return _na(
                    "vs_indicator_data",
                    f"unknown indicator {indicator!r}; known: {', '.join(MACRO_INDICATORS)}. "
                    "For other series pass category_id from vs_categories.",
                )
            cat, tt, sub_default = MACRO_INDICATORS[key]
            if category_id is not None and int(category_id) != cat:
                warnings.append(f"category_id {category_id} ignored: indicator {key} uses {cat}")
            category_id, term_type_id, sub_term_type_id = cat, tt, sub_default
        if category_id is None:
            return _na(
                "vs_indicator_data",
                "pass indicator (GDP/CPI/XK) or category_id (see vs_categories)",
            )
        try:
            ttid = _coerce_id(term_type_id, "term_type_id")
            sub = _coerce_sub(sub_term_type_id)
            out = await _call(
                "vs_indicator_data",
                vs_p.macro_report_data,
                ttid,
                category_id,
                sub or "",
                from_date,
                to_date,
            )
            rows = out.get("rows", []) if isinstance(out, dict) else []
            availability = "available" if rows else "empty"
            return make_envelope(
                out, source="vietstock", availability=availability, warnings=warnings
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_indicator_data", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_trading_info(symbol: str) -> dict[str, Any]:
        """Ceiling, floor, room, EPS, BVPS, PE, PB per symbol. Use for reference snapshot.

        There is no tool named vs_prices or vs_financial_ratios — use this tool
        (snapshot) or financial_ratios (sets) instead."""
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
