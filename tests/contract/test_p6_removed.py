"""P12 contract: removed dead tools stay removed; macro_reports revived (TDD RED)."""

from __future__ import annotations

from typing import Any

from opentrading_mcp.server import create_server, register_preset


def test_dead_tools_absent_from_registry():
    server = create_server("all")
    register_preset(server, "all")
    names = set(server._tool_manager._tools or {})
    for dead in ("vs_reports_search", "vs_stock_industry", "vs_top_liquidity"):
        assert dead not in names, dead


async def test_macro_reports_uses_consensus_scrape(monkeypatch):
    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return [
            {"title": "VCB: Khuyến nghị MUA", "symbol": "VCB", "rating": "MUA",
             "target": 75000.0, "source": "DSC", "date": "26/09/2026", "url": "https://x"},
            {"title": "HPG: Khuyến nghị BÁN", "symbol": "HPG", "rating": "BÁN",
             "target": 20000.0, "source": "VDS", "date": "25/09/2026", "url": "https://y"},
        ]

    import opentrading_mcp.tools.compute as comp_mod

    monkeypatch.setattr(comp_mod, "run_blocking", fake_block)
    server = create_server("scan")
    register_preset(server, "scan")
    tool = server._tool_manager.get_tool("macro_reports")
    assert tool is not None
    env = await tool.fn(symbol="VCB", limit=5)
    assert env["availability"] == "available"
    assert env["data"]["reports"][0]["symbol"] == "VCB"
    assert all(r["symbol"] == "VCB" for r in env["data"]["reports"])
