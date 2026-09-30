"""P6 contract: corp tools dividends_splits + holders (TDD RED)."""

from __future__ import annotations

from typing import Any

from opentrading_mcp.server import create_server, register_preset


def _tool_fn(name: str, preset: str = "scan"):
    server = create_server(preset)
    register_preset(server, preset)
    tool = server._tool_manager.get_tool(name)
    assert tool is not None, f"tool {name} not registered"
    return tool.fn


def _check_envelope(env: dict[str, Any], tool: str) -> None:
    for key in ("data", "provenance", "warnings", "availability"):
        assert key in env, f"{tool}: envelope missing {key!r}"
    assert env["provenance"]["timezone"] == "Asia/Ho_Chi_Minh"


async def test_dividends_vn_returns_cash_dividends(monkeypatch):

    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return [
            {
                "event_code": "DIV",
                "event_title_en": "Cash Dividend - 450 VND",
                "exright_date": "2026-07-23",
                "value_per_share": 450.0,
            },
            {
                "event_code": "ISS",
                "event_title_en": "Bonus Issue ratio 12.8%",
                "exright_date": "2026-04-28",
                "exercise_ratio": 0.1279,
            },
        ]

    import opentrading_mcp.tools.corp as corp_mod

    monkeypatch.setattr(corp_mod, "run_blocking", fake_block)
    fn = _tool_fn("dividends_splits")
    env = await fn(symbol="VCB", region="vn")
    _check_envelope(env, "dividends_splits")
    rows = env["data"]["events"]
    assert len(rows) == 2
    assert rows[0]["is_cash_dividend"] is True
    assert rows[1]["is_share_issue"] is True


async def test_dividends_world_filters_empty_rows(monkeypatch):

    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return [
            {"date": "2024-01-01", "dividends": 0.0, "splits": 0.0},
            {"date": "2024-02-01", "dividends": 0.5, "splits": 0.0},
        ]

    import opentrading_mcp.tools.corp as corp_mod

    monkeypatch.setattr(corp_mod, "run_blocking", fake_block)
    fn = _tool_fn("dividends_splits")
    env = await fn(symbol="AAPL", region="world")
    rows = env["data"]["events"]
    assert len(rows) == 1
    assert rows[0]["dividends"] == 0.5


async def test_holders_vn_returns_shareholders(monkeypatch):
    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return {"symbol": "VCB", "shareholders": [{"owner": "SBV", "pct": 74.0}]}

    import opentrading_mcp.tools.corp as corp_mod

    monkeypatch.setattr(corp_mod, "run_blocking", fake_block)
    fn = _tool_fn("holders")
    env = await fn(symbol="VCB", region="vn")
    _check_envelope(env, "holders")
    assert env["data"]["holders"][0]["owner"] == "SBV"


async def test_holders_world_institutional(monkeypatch):
    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return [{"kind": "institutional", "Holder": "Vanguard", "Shares": 100}]

    import opentrading_mcp.tools.corp as corp_mod

    monkeypatch.setattr(corp_mod, "run_blocking", fake_block)
    fn = _tool_fn("holders")
    env = await fn(symbol="AAPL", region="world", kind="institutional")
    assert env["data"]["kind"] == "institutional"
    assert len(env["data"]["holders"]) == 1


async def test_invalid_region_is_unavailable():
    fn = _tool_fn("dividends_splits")
    env = await fn(symbol="VCB", region="mars")
    assert env["availability"] == "unavailable"


async def test_scan_preset_includes_corp_tools():
    server = create_server("scan")
    tools = register_preset(server, "scan")
    names = {t["name"] for t in tools}
    assert {"dividends_splits", "holders"} <= names
