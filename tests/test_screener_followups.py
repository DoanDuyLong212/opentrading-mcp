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


# --- #44 mục 4: nhánh dữ liệu kiểu cũ không trả NaN/inf ------------------------------


def test_legacy_ratio_paths_skip_non_finite(monkeypatch):
    import sys
    import types

    import pandas as pd

    from opentrading_mcp.providers import vnstock as vn_p

    frame = pd.DataFrame({"P/E": [12.0, float("inf")], "ROE": [0.18, 0.2]})
    assert vn_p._pick_ratio_number(frame, "pe") is None  # newest is inf: not a value
    assert vn_p._pick_ratio_number(frame, "roe") == 0.2

    class _Equity:
        def ratio(self, period: str = "year"):
            return {"pe": float("nan"), "roe": 0.15}

    fundamental = types.SimpleNamespace(equity=lambda s: _Equity())
    fake = types.SimpleNamespace(Fundamental=lambda: fundamental)
    monkeypatch.setitem(sys.modules, "vnstock", fake)
    out = vn_p.equity_fundamentals("AAA")
    assert out["pe"] is None and out["roe"] == 0.15


# --- #44 mục 5: valuation_run hiển thị EPS/BVPS bằng 0 -------------------------------


async def test_valuation_run_echoes_a_reported_zero(monkeypatch):
    from typing import Any

    from opentrading_mcp.server import create_server, register_preset
    from opentrading_mcp.tools import compute_financial as comp_fin

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        if fn is comp_fin.vn_p.equity_quote_batch:
            return [{"symbol": "AAA", "close_price": 10000}]
        if fn is comp_fin.vn_p.equity_fundamentals:
            return {"eps": 0.0, "bvps": 8000.0, "period_label": "2025"}
        return {"data": []}

    monkeypatch.setattr(comp_fin, "_call", fake_call)
    server = create_server("scan")
    register_preset(server, "scan")
    env = await server._tool_manager.get_tool("valuation_run").fn(symbol="AAA")
    data = env["data"]
    assert data["eps"] == 0.0 and "per" not in data  # 0 shown, PER not computed
    assert data["pb"] == 1.25
