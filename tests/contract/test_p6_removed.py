"""P12/P14 contract: removed dead tools stay removed."""

from __future__ import annotations

from opentrading_mcp.server import create_server, register_preset


def test_dead_tools_absent_from_registry():
    server = create_server("all")
    register_preset(server, "all")
    names = set(server._tool_manager._tools or {})
    for dead in (
        "vs_reports_search",
        "vs_stock_industry",
        "vs_top_liquidity",
        "vs_news_search",
        "dnse_foreign_rest",
        "financial_detail",
        "macro_reports",
        "mega_flows",
        "foreign_flow",
        "oracle_health",
    ):
        assert dead not in names, dead
