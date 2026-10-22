"""P5 contract: enriched params for compute.py tools (TDD)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from opentrading_mcp.server import create_server, register_preset

FIXTURES = Path(__file__).parent.parent / "fixtures"


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
    assert env["availability"] in {"available", "empty", "stale", "partial", "unavailable"}


def _install_forensic_fakes(monkeypatch) -> None:
    fd_detail = {
        "symbol": "VCB",
        "statement": "KQKD",
        "unit": "VNDbn",
        "periods": ["Q1/2026", "Q2/2026"],
        "rows": [
            {"norm_id": 2216, "name": "Doanh thu thuần", "values": [100.0, 110.0]},
            {"norm_id": 2217, "name": "Lợi nhuận gộp", "values": [40.0, 44.0]},
            {"norm_id": 990, "name": "Lợi nhuận sau thuế", "values": [20.0, 22.0]},
            {"norm_id": 991, "name": "Chi phí bán hàng", "values": [5.0, 6.0]},
            {"norm_id": 992, "name": "Chi phí quản lý", "values": [8.0, 9.0]},
        ],
    }
    cd_detail = {
        "symbol": "VCB",
        "statement": "CDKT",
        "unit": "VNDbn",
        "periods": ["Q1/2026", "Q2/2026"],
        "rows": [
            {"norm_id": 2996, "name": "TỔNG CỘNG TÀI SẢN", "values": [1000.0, 1100.0]},
            {"norm_id": 3013, "name": "A. TÀI SẢN NGẮN HẠN", "values": [400.0, 440.0]},
            {"norm_id": 2997, "name": "C. NỢ PHẢI TRẢ", "values": [500.0, 520.0]},
            {"norm_id": 3014, "name": "I. Nợ ngắn hạn", "values": [300.0, 320.0]},
            {"norm_id": 2998, "name": "D. VỐN CHỦ SỞ HỮU", "values": [500.0, 580.0]},
            {"norm_id": 3002, "name": "Tiền và tương đương tiền", "values": [100.0, 110.0]},
            {"norm_id": 3005, "name": "III. Các khoản phải thu ngắn hạn", "values": [60.0, 72.0]},
            {"norm_id": 3022, "name": "Phải thu ngắn hạn của khách hàng", "values": [50.0, 60.0]},
        ],
    }
    lc_detail = {
        "symbol": "VCB",
        "statement": "LCTT",
        "unit": "VNDbn",
        "periods": ["Q1/2026", "Q2/2026"],
        "rows": [
            {
                "norm_id": 3100,
                "name": "I. Lưu chuyển tiền thuần từ hoạt động kinh doanh",
                "values": [25.0, 28.0],
            },
        ],
    }

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any):
        stmt = args[1] if len(args) > 1 else None
        if stmt == "KQKD":
            return fd_detail
        if stmt == "CDKT":
            return cd_detail
        return lc_detail

    import opentrading_mcp.tools.compute_financial as comp_fin
    import opentrading_mcp.tools.compute_infra as comp_infra
    import opentrading_mcp.tools.compute_intel as comp_intel

    monkeypatch.setattr(comp_fin, "_call", fake_call)
    monkeypatch.setattr(comp_intel, "_call", fake_call)
    monkeypatch.setattr(comp_infra, "_call", fake_call)


async def test_stock_forensic_detail_includes_series(monkeypatch):
    _install_forensic_fakes(monkeypatch)
    fn = _tool_fn("stock_forensic")
    env = await fn(symbol="VCB", detail=True)
    _check_envelope(env, "stock_forensic")
    assert "series" in env["data"]
    assert env["data"]["f_score"].endswith("/8")
    assert env["data"]["dsri"] is not None
    env2 = await fn(symbol="VCB")
    assert "series" not in env2["data"]


async def test_stock_forensic_m_score_uses_beneish_weights(monkeypatch):
    # Beneish (1999) weights without DEPI: SGAI enters negatively (-0.172).
    _install_forensic_fakes(monkeypatch)
    env = await _tool_fn("stock_forensic")(symbol="VCB")
    d = env["data"]
    weights = {
        "dsri": 0.920,
        "gmi": 0.528,
        "aqi": 0.404,
        "sgi": 0.892,
        "sgai": -0.172,
        "tata": 4.679,
        "lvgi": -0.327,
    }
    assert d["m_partial"] is None
    expected = -4.84 + sum(w * d[k] for k, w in weights.items())
    assert abs(d["m_score"] - expected) < 1e-3


async def test_valuation_run_method_passthrough():
    import inspect

    server = create_server("scan")
    register_preset(server, "scan")
    tool = server._tool_manager.get_tool("valuation_run")
    assert tool is not None
    assert "method" in inspect.signature(tool.fn).parameters


async def test_valuation_run_explicit_method(monkeypatch):

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any):
        if tool == "v":
            return {"EPS": 5.0, "BVPS": 20.0}
        return [{"close_price": 100.0}]

    import opentrading_mcp.tools.compute_financial as comp_fin
    import opentrading_mcp.tools.compute_infra as comp_infra
    import opentrading_mcp.tools.compute_intel as comp_intel

    monkeypatch.setattr(comp_fin, "_call", fake_call)
    monkeypatch.setattr(comp_intel, "_call", fake_call)
    monkeypatch.setattr(comp_infra, "_call", fake_call)
    fn = _tool_fn("valuation_run")
    env = await fn(symbol="VCB", method="dcf")
    _check_envelope(env, "valuation_run")
    assert env["data"]["method"] == "dcf"
    assert env["data"]["per"] == 20.0


async def test_fred_spark_returns_sparkline():
    import inspect

    server = create_server("scan")
    register_preset(server, "scan")
    tool = server._tool_manager.get_tool("fred_series")
    assert tool is not None
    assert "spark" in inspect.signature(tool.fn).parameters


async def test_fred_spark_values(monkeypatch):
    from opentrading_mcp.providers import intel as intel_p

    def fake_series(series_id: str, limit: int = 60):
        assert limit == 5
        return {"points": [{"t": f"2026-0{i}-01", "v": str(i)} for i in range(1, 6)]}

    monkeypatch.setattr(intel_p, "fred_series", fake_series)
    fn = _tool_fn("fred_series")
    env = await fn(series_id="DGS10", limit=5, spark=True)
    _check_envelope(env, "fred_series")
    assert env["data"]["spark"] == ["1", "2", "3", "4", "5"]


async def test_world_macro_limit_slices_points(monkeypatch):
    from opentrading_mcp.providers import intel as intel_p

    def fake_wb(iso3: str, indicator: str):
        return {"points": [{"t": f"202{i}", "v": i} for i in range(10)]}

    monkeypatch.setattr(intel_p, "worldbank_country", fake_wb)
    fn = _tool_fn("world_macro_country")
    env = await fn(iso3="VNM", indicator="NY.GDP.MKTP.KD.ZG", limit=3)
    _check_envelope(env, "world_macro_country")
    assert len(env["data"]["points"]) == 3


async def test_fear_greed_limit_slices_series(monkeypatch):
    from opentrading_mcp.providers import intel as intel_p

    def fake_fg():
        return {"series": [{"t": str(i), "v": i} for i in range(7)]}

    monkeypatch.setattr(intel_p, "fear_greed", fake_fg)
    fn = _tool_fn("world_fear_greed")
    env = await fn(limit=2)
    _check_envelope(env, "world_fear_greed")
    assert len(env["data"]["series"]) == 2


async def test_sentiment_limit_forwarded(monkeypatch):
    from opentrading_mcp.providers import intel as intel_p

    seen: dict[str, Any] = {}

    def fake_posts(symbol: str | None = None, limit: int = 20):
        seen.update(symbol=symbol, limit=limit)
        return []

    monkeypatch.setattr(intel_p, "fireant_posts", fake_posts)
    fn = _tool_fn("sentiment_score")
    env = await fn(symbol="VCB", limit=5)
    _check_envelope(env, "sentiment_score")
    assert seen == {"symbol": "VCB", "limit": 5}


async def test_company_events_types_filters_docs(monkeypatch):

    docs = [
        {"title": "A", "kind": "bctc"},
        {"title": "B", "kind": "nghi_quyet"},
        {"title": "C", "kind": "bctc"},
    ]

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any):
        return docs

    import opentrading_mcp.tools.compute_financial as comp_fin
    import opentrading_mcp.tools.compute_infra as comp_infra
    import opentrading_mcp.tools.compute_intel as comp_intel

    monkeypatch.setattr(comp_fin, "_call", fake_call)
    monkeypatch.setattr(comp_intel, "_call", fake_call)
    monkeypatch.setattr(comp_infra, "_call", fake_call)
    fn = _tool_fn("company_events")
    env = await fn(symbol="VCB", types="bctc")
    _check_envelope(env, "company_events")
    assert [d["title"] for d in env["data"]["events"]] == ["A", "C"]


async def test_financial_statements_statement_and_periods(monkeypatch):
    raw = json.loads((FIXTURES / "financeinfo_fpt_quarter.json").read_text(encoding="utf-8"))

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any):
        return raw

    import opentrading_mcp.tools.compute_financial as comp_fin
    import opentrading_mcp.tools.compute_infra as comp_infra
    import opentrading_mcp.tools.compute_intel as comp_intel

    monkeypatch.setattr(comp_fin, "_call", fake_call)
    monkeypatch.setattr(comp_intel, "_call", fake_call)
    monkeypatch.setattr(comp_infra, "_call", fake_call)
    fn = _tool_fn("financial_statements")
    env = await fn(symbol="FPT", statement="kqkd", periods_n=2)
    _check_envelope(env, "financial_statements")
    assert env["warnings"] == []
    assert env["data"]["periods"] == ["Q1/2026", "Q2/2026"]
    assert list(env["data"]["statements"]) == ["Kết quả kinh doanh"]
    revenue = env["data"]["statements"]["Kết quả kinh doanh"][0]
    assert revenue["values"] == {"Q1/2026": 12479997206775.0, "Q2/2026": 13788503461199.0}


async def test_financial_ratios_peers_merged(monkeypatch):

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any):
        return {"EPS": 1.0}

    import opentrading_mcp.tools.compute_financial as comp_fin
    import opentrading_mcp.tools.compute_infra as comp_infra
    import opentrading_mcp.tools.compute_intel as comp_intel

    monkeypatch.setattr(comp_fin, "_call", fake_call)
    monkeypatch.setattr(comp_intel, "_call", fake_call)
    monkeypatch.setattr(comp_infra, "_call", fake_call)
    fn = _tool_fn("financial_ratios")
    env = await fn(symbol="VCB", peers=["HPG", "SSI"])
    _check_envelope(env, "financial_ratios")
    assert len(env["data"]["peers"]) == 2
    assert env["data"]["peers"][0]["symbol"] == "HPG"


async def test_peer_compare_metrics_filters_keys(monkeypatch):

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any):
        return {"EPS": 1.0, "BVPS": 2.0, "PE": 3.0}

    import opentrading_mcp.tools.compute_financial as comp_fin
    import opentrading_mcp.tools.compute_infra as comp_infra
    import opentrading_mcp.tools.compute_intel as comp_intel

    monkeypatch.setattr(comp_fin, "_call", fake_call)
    monkeypatch.setattr(comp_intel, "_call", fake_call)
    monkeypatch.setattr(comp_infra, "_call", fake_call)
    fn = _tool_fn("peer_compare")
    env = await fn(symbol="VCB", peers=["HPG"], metrics=["pe", "eps"])
    _check_envelope(env, "peer_compare")
    row = env["data"]["rows"][1]
    assert set(row) == {"symbol", "EPS", "PE"}


async def test_pattern_match_limit_top_n(monkeypatch):
    import opentrading_mcp.tools.compute_financial as comp_fin
    import opentrading_mcp.tools.compute_infra as comp_infra
    import opentrading_mcp.tools.compute_intel as comp_intel

    candles = [{"c": float(100 + i)} for i in range(120)]

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any):
        return candles

    monkeypatch.setattr(comp_fin, "_call", fake_call)
    monkeypatch.setattr(comp_intel, "_call", fake_call)
    monkeypatch.setattr(comp_infra, "_call", fake_call)
    fn = _tool_fn("pattern_match")
    env = await fn(symbol="VCB", lookback=60, limit=3)
    _check_envelope(env, "pattern_match")
    assert len(env["data"]["matches"]) == 3
    corrs = [m["corr"] for m in env["data"]["matches"]]
    assert corrs == sorted(corrs, reverse=True)


async def test_event_stats_limit(monkeypatch):
    from opentrading_mcp.providers import intel as intel_p

    seen: dict[str, Any] = {}

    def fake_gdelt(query: str = "stock market", max_records: int = 20):
        seen.update(query=query, max_records=max_records)
        return {"articles": []}

    monkeypatch.setattr(intel_p, "gdelt_events", fake_gdelt)
    fn = _tool_fn("event_stats")
    env = await fn(query="rate hike", limit=5)
    _check_envelope(env, "event_stats")
    assert seen == {"query": "rate hike", "max_records": 5}


async def test_compare_assets_timeframe_recorded(monkeypatch):
    from opentrading_mcp.providers import yfinance as yf_p

    seen: dict[str, Any] = {}

    def fake_batch(tickers: list[str], period: str = "2d", interval: str = "1d"):
        seen.update(tickers=tickers, period=period, interval=interval)
        return [{"ticker": tickers[0]}]

    monkeypatch.setattr(yf_p, "batch_last", fake_batch)
    fn = _tool_fn("compare_assets")
    env = await fn(assets=["GC=F"], timeframe="1wk")
    _check_envelope(env, "compare_assets")
    assert seen == {"tickers": ["GC=F"], "period": "3mo", "interval": "1wk"}


async def test_runs_list_id_filters(monkeypatch):
    import opentrading_mcp.tools.compute_infra as comp_infra

    rows = [{"run_id": "a1"}, {"run_id": "b2"}]
    monkeypatch.setattr(comp_infra, "_read_runs", lambda: rows)
    fn = _tool_fn("runs_list")
    env = await fn(id="b")
    _check_envelope(env, "runs_list")
    assert env["data"]["runs"] == [{"run_id": "b2"}]
