"""Screener sau review 24/10: P/E âm và khoảng lọc rỗng (#44 mục 1)."""

from __future__ import annotations


def test_negative_pe_does_not_pass_an_upper_bound():
    from opentrading_mcp.providers.screener import apply_filters

    rows = [{"symbol": "NVL", "pe": -3.1}, {"symbol": "FPT", "pe": 9.5}, {"symbol": "X", "pe": 0.0}]
    assert [r["symbol"] for r in apply_filters(rows, {"pe": [None, 10]})] == ["FPT"]
    # chỉ cận dưới: không thêm điều kiện dương (người dùng tự chọn khoảng)
    assert [r["symbol"] for r in apply_filters(rows, {"pe": [-5, None]})] == ["NVL", "FPT", "X"]


async def test_empty_range_is_not_a_required_metric(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p
    from opentrading_mcp.server import create_server, register_preset

    monkeypatch.setattr(vn_p, "listing_symbols", lambda: [{"symbol": "AAA"}, {"symbol": "BBB"}])
    monkeypatch.setattr(
        vn_p, "equity_fundamentals",
        lambda symbol, period="year": {"symbol": symbol, "roe": 0.2, "period_label": "2025"},
    )
    server = create_server("scan")
    register_preset(server, "scan")
    env = await server._tool_manager.get_tool("stock_screener").fn(
        filters={"pe": [None, None]}, limit=5
    )
    assert env["data"]["filters"] == {}
    assert not any("pe missing" in w for w in env["warnings"])
    assert [c["symbol"] for c in env["data"]["candidates"]] == ["AAA", "BBB"]
