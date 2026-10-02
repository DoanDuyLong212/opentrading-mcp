"""P12/P14 contract: removed dead tools stay removed."""

from __future__ import annotations

from typing import Any

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
        "macro_reports",
        "mega_flows",
        "foreign_flow",
        "oracle_health",
    ):
        assert dead not in names, dead


async def test_planned_targets_and_detail_live_wiring(monkeypatch):
    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        from opentrading_mcp.providers import vietstock as vs_mod

        target = getattr(fn, "func", None)
        if target is vs_mod.planned_targets:
            return {
                "symbol": "FPT",
                "unit": "VNDbn",
                "years": [2025, 2026],
                "rows": [
                    {
                        "name": "Doanh thu kế hoạch",
                        "planned_target_id": 5,
                        "plan": {"2025": 75400.0, "2026": 58580.0},
                    }
                ],
            }
        if target is vs_mod.financial_detail:
            return {
                "symbol": "FPT",
                "statement": "KQKD",
                "unit": "VNDbn",
                "periods": ["Q4/2025", "Q2/2026"],
                "rows": [
                    {"norm_id": 2216, "name": "Doanh thu thuần", "values": [20225.0, 13789.0]}
                ],
            }
        raise AssertionError(f"unexpected {target}")

    import opentrading_mcp.tools.corp as corp_mod

    monkeypatch.setattr(corp_mod, "run_blocking", fake_block)
    server = create_server("scan")
    register_preset(server, "scan")
    for name in ("planned_targets", "financial_detail"):
        assert server._tool_manager.get_tool(name) is not None, name
    env = await server._tool_manager.get_tool("planned_targets").fn(symbol="FPT")
    assert env["availability"] == "available"
    assert env["data"]["rows"][0]["plan"]["2026"] == 58580.0
    env2 = await server._tool_manager.get_tool("financial_detail").fn(
        symbol="FPT", statement="KQKD"
    )
    assert env2["availability"] == "available"
    assert env2["data"]["rows"][0]["values"] == [20225.0, 13789.0]
