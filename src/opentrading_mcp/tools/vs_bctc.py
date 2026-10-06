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
            terms = await _call("t", vs_p.financial_terms)
            return make_envelope({"terms": terms}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_financial_terms", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_financial_norms(btype: int = 1) -> dict[str, Any]:
        """190+ BCTC line items for a business type. Use to resolve norm ids.

        btype: 1 CTCP (general), 2 securities, 3 bank, 5 insurance.
        """
        try:
            data = await _call("n", vs_p.financial_norms, btype)
            rows = data if isinstance(data, list) else data.get("data", [])
            return make_envelope(
                {"btype": btype, "count": len(rows), "norms": rows}, source="vietstock"
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_financial_norms", str(exc))

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
        """Filings and disclosures with links. Use for corporate actions.

        page_size: max documents returned (default 60).
        """
        try:
            return make_envelope(
                {"docs": await _call("d", vs_p.documents, symbol, page_size)},
                source="vietstock",
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_documents", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vs_industry_tree() -> dict[str, Any]:
        """GICS industry tree. Use before sector mapping."""
        try:
            return make_envelope({"tree": await _call("t", vs_p.industry_tree)}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("vs_industry_tree", str(exc))

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
    async def vs_gics_index(group: int = 1) -> dict[str, Any]:
        """GICS index closes with foreign flow. Use for sector context.

        group: index set (1, 2 or 3 return different groups).
        """
        try:
            return make_envelope(
                {"group": group, "rows": await _call("g", vs_p.gics_index, group)},
                source="vietstock",
            )
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
    async def vs_market_info(exchange: str = "HOSE") -> dict[str, Any]:
        """Per-exchange board row: index, breadth, put-through. Use for 5s snapshots in hours.

        exchange: HOSE, HNX or UPCOM (endpoint is per-exchange, not per-symbol).
        """
        try:
            return make_envelope(
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
        list_id = 64 if direction == "xk" else 65
        import datetime

        frm = from_date or f"{datetime.date.today().year}-01-01"
        try:
            out = await _call("x", vs_p.macro_report_data, 2, list_id, "", frm)
            rows = out.get("rows", []) if isinstance(out, dict) else []
            availability = "available" if rows else "empty"
            return make_envelope(
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
