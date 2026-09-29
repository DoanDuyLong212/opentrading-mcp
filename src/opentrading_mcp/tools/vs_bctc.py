"""Vietstock paid/report/industry tools (BCTC flow, documents, industry, flows)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.providers import vietstock as vs_p
from opentrading_mcp.providers.errors import (
    ProviderAuthMissing,
    ProviderBadData,
    ProviderUnavailable,
)
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import READ_ONLY, run_blocking
from opentrading_mcp.tools.vs import _na


async def _call(tool: str, fn: Any, *args: Any) -> Any:
    import functools

    return await run_blocking(functools.partial(fn, *args), tool, timeout_secs=60.0)


def register_vs_bctc_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def vs_financial_terms() -> dict[str, Any]:
        """Report term catalogue (annual, Q1-Q4, H1, 9M). Use before BCTC value queries."""
        try:
            return make_envelope({"terms": await _call("t", vs_p.financial_terms)}, source="v")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_financial_terms", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_financial_norms(btype: int = 1) -> dict[str, Any]:
        """190+ BCTC line items for a business type. Use to resolve norm ids."""
        try:
            data = await _call("n", vs_p.financial_norms, btype)
            rows = data if isinstance(data, list) else data.get("data", [])
            return make_envelope({"btype": btype, "count": len(rows), "norms": rows}, source="v")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_financial_norms", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_financial_values(
        symbol: str, btype: int = 1, years: int = 3, tids: list[int] | None = None
    ) -> dict[str, Any]:
        """Paid BCTC values matrix (default tids [2,3,4,5,9]). Use for statements."""
        try:
            data = await _call("v", vs_p.financial_values, symbol, btype, years, tids)
            return make_envelope(data, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_financial_values", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_company_info(symbol: str) -> dict[str, Any]:
        """Company names, exchange and description. Use for profiles."""
        try:
            return make_envelope(
                {"info": await _call("c", vs_p.company_info, symbol)}, source="vietstock"
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_company_info", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_overview_trading(symbol: str) -> dict[str, Any]:
        """EPS, BVPS, PE, PB, ROEA/ROAA snapshot. Use for valuation inputs."""
        try:
            return make_envelope(
                {"overview": await _call("o", vs_p.overview_trading, symbol)},
                source="vietstock",
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_overview_trading", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_documents(symbol: str, page_size: int = 60) -> dict[str, Any]:
        """Filings and disclosures with links. Use for corporate actions."""
        try:
            return make_envelope(
                {"docs": await _call("d", vs_p.documents, symbol, page_size)},
                source="vietstock",
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_documents", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_reports_search(
        symbol: str = "", keywords: str | None = None, page_size: int = 50
    ) -> dict[str, Any]:
        """Analyst reports search. Use for external views on a name."""
        try:
            return make_envelope(
                {"reports": await _call("r", vs_p.reports_search, symbol, page_size, keywords)},
                source="vietstock",
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_reports_search", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_industry_tree() -> dict[str, Any]:
        """GICS industry tree. Use before sector mapping."""
        try:
            return make_envelope({"tree": await _call("t", vs_p.industry_tree)}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_industry_tree", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_stock_industry(industry_id: int) -> dict[str, Any]:
        """Companies under a GICS industry node. Use for peer universes."""
        try:
            data = await _call("s", vs_p.stock_industry, industry_id)
            return make_envelope({"industry": industry_id, "stocks": data}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_stock_industry", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_industry_heatmap() -> dict[str, Any]:
        """Live sector heatmap. Use for intraday rotation."""
        try:
            return make_envelope(
                {"heatmap": await _call("h", vs_p.industry_heatmap)}, source="vietstock"
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_industry_heatmap", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_selftrading() -> dict[str, Any]:
        """Prop-desk flow chart. Use alongside foreign flows."""
        try:
            return make_envelope({"flow": await _call("s", vs_p.selftrading)}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_selftrading", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_top_liquidity(index: str = "VNINDEX", top_n: int = 20) -> dict[str, Any]:
        """Most liquid names per index. Use for liquidity screens."""
        try:
            rows = await _call("l", vs_p.top_liquidity, index)
            if isinstance(rows, list):
                rows = rows[: max(int(top_n), 1)]
            return make_envelope({"rows": rows}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_top_liquidity", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_gics_index() -> dict[str, Any]:
        """GICS index closes with foreign flow. Use for sector context."""
        try:
            return make_envelope({"rows": await _call("g", vs_p.gics_index)}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_gics_index", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_currency() -> dict[str, Any]:
        """Reference FX table. Use as fallback FX source."""
        try:
            return make_envelope({"rows": await _call("c", vs_p.currency)}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_currency", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_market_info(symbol: str = "") -> dict[str, Any]:
        """Compact market line per symbol. Use for 5s snapshots in hours."""
        try:
            return make_envelope(
                {"info": await _call("m", vs_p.market_info, symbol)}, source="vietstock"
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_market_info", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_news_search(query: str, page_size: int = 20, page: int = 1) -> dict[str, Any]:
        """Vietstock article search. Use for catalyst lookup."""
        try:
            window = max(int(page_size), 1) * max(int(page), 1)
            data = await _call("n", vs_p.news_search, query, window)
            if isinstance(data, list) and page > 1:
                start = (page - 1) * page_size
                data = data[start : start + page_size]
            return make_envelope({"articles": data}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_news_search", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_xnk_detail(
        direction: str = "xk", from_date: str | None = None, to_date: str | None = None
    ) -> dict[str, Any]:
        """Import/export by country. Use for trade structure (termType 2)."""
        list_id = 64 if direction == "xk" else 65
        try:
            data = await _call(
                "x",
                vs_p._post,
                "/Macro/GetReportDataByIDs",
                {
                    "termTypeID": 2,
                    "subTermTypeID": "",
                    "fromDate": from_date or "2021-01-01",
                    "toDate": to_date or "",
                    "type": "CATEGORY",
                    "listID[]": list_id,
                },
            )
            return make_envelope({"direction": direction, "data": data}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_xnk_detail", str(exc))

    return [
        {"name": "vs_financial_terms"},
        {"name": "vs_financial_norms"},
        {"name": "vs_financial_values"},
        {"name": "vs_company_info"},
        {"name": "vs_overview_trading"},
        {"name": "vs_documents"},
        {"name": "vs_reports_search"},
        {"name": "vs_industry_tree"},
        {"name": "vs_stock_industry"},
        {"name": "vs_industry_heatmap"},
        {"name": "vs_selftrading"},
        {"name": "vs_top_liquidity"},
        {"name": "vs_gics_index"},
        {"name": "vs_currency"},
        {"name": "vs_market_info"},
        {"name": "vs_news_search"},
        {"name": "vs_xnk_detail"},
    ]
