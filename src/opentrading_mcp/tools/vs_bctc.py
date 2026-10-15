"""Vietstock paid/report/industry tools (BCTC flow, documents, industry, flows)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.cache import TTL_SECONDS
from opentrading_mcp.providers import vietstock as vs_p
from opentrading_mcp.providers.errors import (
    ProviderAuthMissing,
    ProviderBadData,
    ProviderUnavailable,
)
from opentrading_mcp.tools.shared import (
    READ_ONLY,
    cache_lookup,
    cache_store,
    price_ttl,
    run_blocking,
)
from opentrading_mcp.tools.vs import _na


async def _call(tool: str, fn: Any, *args: Any) -> Any:
    import functools

    return await run_blocking(functools.partial(fn, *args), tool, timeout_secs=60.0)


def register_vs_bctc_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def vs_financial_terms() -> dict[str, Any]:
        """Report term catalogue (annual, Q1-Q4, H1, 9M). Use before BCTC value queries."""
        hit = await cache_lookup("vs_financial_terms", "-")
        if hit is not None:
            return hit
        try:
            terms = await _call("t", vs_p.financial_terms)
            return await cache_store(
                "vs_financial_terms", "-", TTL_SECONDS["categories"],
                {"terms": terms}, source="vietstock",
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_financial_terms", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_financial_norms(btype: int = 1) -> dict[str, Any]:
        """190+ BCTC line items for a business type. Use to resolve norm ids.

        btype: 1 CTCP (general), 2 securities, 3 bank, 5 insurance.
        """
        fp = f"{btype}"
        hit = await cache_lookup("vs_financial_norms", fp)
        if hit is not None:
            return hit
        try:
            data = await _call("n", vs_p.financial_norms, btype)
            rows = data if isinstance(data, list) else data.get("data", [])
            return await cache_store(
                "vs_financial_norms", fp, TTL_SECONDS["categories"],
                {"btype": btype, "count": len(rows), "norms": rows}, source="vietstock",
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_financial_norms", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_company_info(symbol: str) -> dict[str, Any]:
        """Tên công ty, sàn và mô tả. Dùng khi cần hồ sơ ngắn gọn.

        Dùng khi: "FPT là công ty gì, niêm yết ở đâu".
        Không dùng khi: cần cổ đông/lãnh đạo (dùng vn_company với detail=true); cần dossier giá + hồ
            sơ (dùng stock_overview).

        Ví dụ: {"symbol": "FPT"}.
        """
        fp = f"{symbol}"
        hit = await cache_lookup("vs_company_info", fp)
        if hit is not None:
            return hit
        try:
            return await cache_store(
                "vs_company_info", fp, TTL_SECONDS["financeinfo"],  # static profile
                {"info": await _call("c", vs_p.company_info, symbol)}, source="vietstock",
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_company_info", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_overview_trading(symbol: str) -> dict[str, Any]:
        """Snapshot EPS, BVPS, PE, PB, ROEA/ROAA. Dùng làm input định giá nhanh.

        Dùng khi: cần bội số hiện tại của 1 mã để so sánh.
        Không dùng khi: cần vùng giá trị hợp lý (dùng valuation_run); cần so nhiều mã cùng lúc (dùng
            peer_compare hoặc financial_ratios với peers).
        """
        fp = f"{symbol}"
        hit = await cache_lookup("vs_overview_trading", fp)
        if hit is not None:
            return hit
        try:
            return await cache_store(
                "vs_overview_trading", fp, price_ttl(),  # per-symbol trading snapshot
                {"overview": await _call("o", vs_p.overview_trading, symbol)},
                source="vietstock",
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_overview_trading", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_documents(symbol: str, page_size: int = 60) -> dict[str, Any]:
        """Filings and disclosures with links. Use for corporate actions.

        page_size: max documents returned (default 60).
        """
        fp = f"{symbol}|{page_size}"
        hit = await cache_lookup("vs_documents", fp)
        if hit is not None:
            return hit
        try:
            return await cache_store(
                "vs_documents", fp, TTL_SECONDS["documents"],
                {"docs": await _call("d", vs_p.documents, symbol, page_size)},
                source="vietstock",
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_documents", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_industry_tree() -> dict[str, Any]:
        """GICS industry tree. Use before sector mapping."""
        hit = await cache_lookup("vs_industry_tree", "-")
        if hit is not None:
            return hit
        try:
            return await cache_store(
                "vs_industry_tree", "-", TTL_SECONDS["categories"],
                {"tree": await _call("t", vs_p.industry_tree)}, source="vietstock",
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_industry_tree", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_industry_heatmap() -> dict[str, Any]:
        """Live sector heatmap. Use for intraday rotation."""
        hit = await cache_lookup("vs_industry_heatmap", "-")
        if hit is not None:
            return hit
        try:
            return await cache_store(
                "vs_industry_heatmap", "-", TTL_SECONDS["world"],
                {"heatmap": await _call("h", vs_p.industry_heatmap)}, source="vietstock",
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_industry_heatmap", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_selftrading() -> dict[str, Any]:
        """Prop-desk flow chart. Use alongside foreign flows."""
        hit = await cache_lookup("vs_selftrading", "-")
        if hit is not None:
            return hit
        try:
            return await cache_store(
                "vs_selftrading", "-", TTL_SECONDS["hour"],
                {"flow": await _call("s", vs_p.selftrading)}, source="vietstock",
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_selftrading", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_gics_index(group: int = 1) -> dict[str, Any]:
        """GICS index closes with foreign flow. Use for sector context.

        group: index set (1, 2 or 3 return different groups).
        """
        fp = f"{group}"
        hit = await cache_lookup("vs_gics_index", fp)
        if hit is not None:
            return hit
        try:
            return await cache_store(
                "vs_gics_index", fp, price_ttl(),
                {"group": group, "rows": await _call("g", vs_p.gics_index, group)},
                source="vietstock",
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_gics_index", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_currency() -> dict[str, Any]:
        """Reference FX table. Use as fallback FX source."""
        hit = await cache_lookup("vs_currency", "-")
        if hit is not None:
            return hit
        try:
            return await cache_store(
                "vs_currency", "-", TTL_SECONDS["hour"],
                {"rows": await _call("c", vs_p.currency)}, source="vietstock",
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_currency", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_market_info(exchange: str = "HOSE") -> dict[str, Any]:
        """Per-exchange board row: index, breadth, put-through. Use for 5s snapshots in hours.

        exchange: HOSE, HNX or UPCOM (endpoint is per-exchange, not per-symbol).
        """
        fp = f"{exchange}"
        hit = await cache_lookup("vs_market_info", fp)
        if hit is not None:
            return hit
        try:
            return await cache_store(
                "vs_market_info", fp, price_ttl(),
                {
                    "exchange": exchange.strip().upper(),
                    "rows": await _call("m", vs_p.market_info_board, exchange),
                },
                source="vietstock",
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_market_info", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_xnk_detail(direction: str = "xk", from_date: str | None = None) -> dict[str, Any]:
        """Import/export by country via browser-session replay. Use for trade structure.

        direction: 'xk' exports (cat 64), 'nk' imports (65). termType monthly,
        from_date default current year (ISO). Standard pack serves it; rows
        {name=country, group, period, year, value 'Triệu USD', timeorder}.
        """
        fp = f"{direction}|{from_date}"
        hit = await cache_lookup("vs_xnk_detail", fp)
        if hit is not None:
            return hit
        list_id = 64 if direction == "xk" else 65
        import datetime

        frm = from_date or f"{datetime.date.today().year}-01-01"
        try:
            out = await _call("x", vs_p.macro_report_data, 2, list_id, "", frm)
            rows = out.get("rows", []) if isinstance(out, dict) else []
            availability = "available" if rows else "empty"
            return await cache_store(
                "vs_xnk_detail", fp, TTL_SECONDS["documents"],
                {"direction": direction, **out}, source="vietstock", availability=availability
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_xnk_detail", str(exc))

    return [
        {"name": "vs_financial_terms"},
        {"name": "vs_financial_norms"},
        {"name": "vs_company_info"},
        {"name": "vs_overview_trading"},
        {"name": "vs_documents"},
        {"name": "vs_industry_tree"},
        {"name": "vs_industry_heatmap"},
        {"name": "vs_selftrading"},
        {"name": "vs_gics_index"},
        {"name": "vs_currency"},
        {"name": "vs_market_info"},
        {"name": "vs_xnk_detail"},
    ]
