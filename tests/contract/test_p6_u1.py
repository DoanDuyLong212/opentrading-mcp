"""P6 contract: U1 screener technical stage (TDD RED)."""

from __future__ import annotations

from typing import Any

from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.server import create_server, register_preset


def _tool_fn(name: str, preset: str = "scan"):
    server = create_server(preset)
    register_preset(server, preset)
    tool = server._tool_manager.get_tool(name)
    assert tool is not None, f"tool {name} not registered"
    return tool.fn


async def test_screener_technical_stage_filters(monkeypatch):
    import opentrading_mcp.tools.scan as scan_mod

    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        target = getattr(fn, "func", fn)
        if target is vn_p.listing_symbols:
            return [
                {"symbol": "VCB", "exchange": "HOSE"},
                {"symbol": "HPG", "exchange": "HOSE"},
            ]
        if target is vn_p.equity_fundamentals:
            return {"pe": 10.0, "roe": 0.2}
        if target is vn_p.quote_history:
            return [
                {"t": f"2026-01-{d:02d}", "o": 10.0, "h": 10.2, "l": 9.8, "c": 10.0, "v": 100.0}
                for d in range(1, 61)
            ]
        raise AssertionError(f"unexpected upstream {target}")

    monkeypatch.setattr(scan_mod, "run_blocking", fake_block)
    fn = _tool_fn("stock_screener")
    env = await fn(filters={"exchange": "HOSE"}, technical={"rsi_lt": 60.0}, limit=5)
    assert len(env["data"]["candidates"]) == 2
    env2 = await fn(filters={"exchange": "HOSE"}, technical={"rsi_lt": 40.0}, limit=5)
    assert env2["data"]["candidates"] == []


async def test_screener_bad_technical_rule_is_unavailable(monkeypatch):
    import opentrading_mcp.tools.scan as scan_mod

    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return [{"symbol": "VCB", "exchange": "HOSE"}]

    monkeypatch.setattr(scan_mod, "run_blocking", fake_block)
    fn = _tool_fn("stock_screener")
    env = await fn(filters={"exchange": "HOSE"}, technical={"nope": 1})
    assert env["availability"] == "unavailable"
