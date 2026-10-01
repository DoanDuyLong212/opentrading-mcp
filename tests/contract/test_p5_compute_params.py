"""P5 contract: enriched params for compute.py tools (TDD)."""

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
    assert env["availability"] in {"available", "empty", "stale", "partial", "unavailable"}


async def test_stock_forensic_detail_includes_series(monkeypatch):

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any):
        return {
            "revenue_q1": 10.0,
            "revenue_q2": 8.0,
            "receivables_q1": 5.0,
            "receivables_q2": 4.0,
            "total assets": 100.0,
        }

    import opentrading_mcp.tools.compute as comp_mod

    monkeypatch.setattr(comp_mod, "_call", fake_call)
    fn = _tool_fn("stock_forensic")
    env = await fn(symbol="VCB", detail=True)
    _check_envelope(env, "stock_forensic")
    assert "series" in env["data"]
    env2 = await fn(symbol="VCB")
    assert "series" not in env2["data"]


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

    import opentrading_mcp.tools.compute as comp_mod

    monkeypatch.setattr(comp_mod, "_call", fake_call)
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

    import opentrading_mcp.tools.compute as comp_mod

    monkeypatch.setattr(comp_mod, "_call", fake_call)
    fn = _tool_fn("company_events")
    env = await fn(symbol="VCB", types="bctc")
    _check_envelope(env, "company_events")
    assert [d["title"] for d in env["data"]["events"]] == ["A", "C"]


async def test_financial_statements_statement_and_periods(monkeypatch):

    pages = [
        {"KQKD": [{"q": 1}, {"q": 2}, {"q": 3}]},
        {"CDKT": [{"q": 1}]},
    ]

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any):
        return {"pages": pages}

    import opentrading_mcp.tools.compute as comp_mod

    monkeypatch.setattr(comp_mod, "_call", fake_call)
    fn = _tool_fn("financial_statements")
    env = await fn(symbol="VCB", statement="kqkd", periods_n=2)
    _check_envelope(env, "financial_statements")
    assert env["data"]["periods"] == [{"q": 1}, {"q": 2}]


async def test_financial_ratios_peers_merged(monkeypatch):

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any):
        return {"EPS": 1.0}

    import opentrading_mcp.tools.compute as comp_mod

    monkeypatch.setattr(comp_mod, "_call", fake_call)
    fn = _tool_fn("financial_ratios")
    env = await fn(symbol="VCB", peers=["HPG", "SSI"])
    _check_envelope(env, "financial_ratios")
    assert len(env["data"]["peers"]) == 2
    assert env["data"]["peers"][0]["symbol"] == "HPG"


async def test_peer_compare_metrics_filters_keys(monkeypatch):

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any):
        return {"EPS": 1.0, "BVPS": 2.0, "PE": 3.0}

    import opentrading_mcp.tools.compute as comp_mod

    monkeypatch.setattr(comp_mod, "_call", fake_call)
    fn = _tool_fn("peer_compare")
    env = await fn(symbol="VCB", peers=["HPG"], metrics=["pe", "eps"])
    _check_envelope(env, "peer_compare")
    row = env["data"]["rows"][1]
    assert set(row) == {"symbol", "EPS", "PE"}


async def test_pattern_match_limit_top_n(monkeypatch):
    import opentrading_mcp.tools.compute as comp_mod

    candles = [{"c": float(100 + i)} for i in range(120)]

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any):
        return candles

    monkeypatch.setattr(comp_mod, "_call", fake_call)
    fn = _tool_fn("pattern_match")
    env = await fn(symbol="VCB", lookback=60, limit=3)
    _check_envelope(env, "pattern_match")
    assert len(env["data"]["matches"]) == 3
    corrs = [m["corr"] for m in env["data"]["matches"]]
    assert corrs == sorted(corrs, reverse=True)


async def test_trade_log_days_side_filter(monkeypatch):
    import opentrading_mcp.tools.compute as comp_mod

    rows = [
        {"side": "buy", "date": "2026-09-20"},
        {"side": "sell", "date": "2026-09-21"},
        {"side": "buy", "date": "2020-01-01"},
    ]
    monkeypatch.setattr(comp_mod, "_read_trade_log", lambda: rows)
    fn = _tool_fn("signals_trade_log")
    env = await fn(days=365, side="buy")
    _check_envelope(env, "signals_trade_log")
    assert len(env["data"]["trades"]) == 1
    assert env["data"]["trades"][0]["date"] == "2026-09-20"


async def test_macro_reports_limit(monkeypatch):
    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return [
            {"title": "VCB: MUA", "symbol": "VCB", "rating": "MUA"},
            {"title": "HPG: BÁN", "symbol": "HPG", "rating": "BÁN"},
        ]

    import opentrading_mcp.tools.compute as comp_mod

    monkeypatch.setattr(comp_mod, "run_blocking", fake_block)
    fn = _tool_fn("macro_reports")
    env = await fn(symbol="VCB", limit=7)
    _check_envelope(env, "macro_reports")
    assert env["data"]["symbol"] == "VCB"
    assert all(r["symbol"] == "VCB" for r in env["data"]["reports"])


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
    import opentrading_mcp.tools.compute as comp_mod

    rows = [{"run_id": "a1"}, {"run_id": "b2"}]
    monkeypatch.setattr(comp_mod, "_read_runs", lambda: rows)
    fn = _tool_fn("runs_list")
    env = await fn(id="b")
    _check_envelope(env, "runs_list")
    assert env["data"]["runs"] == [{"run_id": "b2"}]
