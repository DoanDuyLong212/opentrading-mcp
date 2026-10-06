"""P5 contract: enriched params for quant/scan/intel tools (TDD)."""

from __future__ import annotations

from typing import Any

from opentrading_mcp.server import create_server, register_preset


def _tool_fn(name: str, preset: str):
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


async def test_quant_backtest_strategy_params(monkeypatch):

    candles = [{"c": 100.0 + i} for i in range(10)]

    async def fake_rb(fn: Any, tool: str, timeout_secs: float = 90.0):
        return candles

    import opentrading_mcp.tools.quant_backtest as quant_mod

    monkeypatch.setattr(quant_mod, "run_blocking", fake_rb)
    fn = _tool_fn("quant_backtest", "quant")
    env = await fn(
        symbol="VCB", cost_bps=10.0, strategy="buy_hold", slippage_bps=5.0, benchmark="VNINDEX"
    )
    _check_envelope(env, "quant_backtest")
    assert env["data"]["strategy"] == "buy_hold"
    assert env["data"]["benchmark"] == "VNINDEX"
    assert env["data"]["slippage_bps"] == 5.0
    # net = gross - (10+5)/10000*2 ; gross = 109/100-1 = 0.09
    assert env["data"]["net_return"] == round(0.09 - 15 / 10000 * 2, 4)


async def test_quant_risk_annualizes(monkeypatch):
    fn = _tool_fn("quant_risk", "quant")
    env = await fn(returns=[0.01, -0.02, 0.03], periods_per_year=252)
    _check_envelope(env, "quant_risk")
    import statistics

    rets = [0.01, -0.02, 0.03]
    expected = round(statistics.fmean(rets) / statistics.pstdev(rets) * (252**0.5), 4)
    assert env["data"]["sharpe_proxy"] == expected
    assert env["data"]["periods_per_year"] == 252


async def test_quant_factors_lookback(monkeypatch):

    candles = [{"c": 100.0 + i * 0.5} for i in range(100)]

    async def fake_rb(fn: Any, tool: str, timeout_secs: float = 60.0):
        return candles

    import opentrading_mcp.tools.quant_stats as quant_mod

    monkeypatch.setattr(quant_mod, "run_blocking", fake_rb)
    fn = _tool_fn("quant_factors", "quant")
    env = await fn(symbol="VCB", lookback=40)
    _check_envelope(env, "quant_factors")
    assert env["data"]["lookback"] == 40
    assert "max_dd_full_pct" in env["data"]


async def test_signals_technical_indicators_filter(monkeypatch):
    import opentrading_mcp.tools.scan as scan_mod

    candles = [
        {"t": i, "o": 100.0 + i, "h": 101.0 + i, "l": 99.0 + i, "c": 100.5 + i, "v": 10.0}
        for i in range(250)
    ]

    async def fake_rb(fn: Any, tool: str, timeout_secs: float = 60.0):
        return candles

    monkeypatch.setattr(scan_mod, "run_blocking", fake_rb)
    fn = _tool_fn("signals_technical", "scan")
    env = await fn(symbol="VCB", indicators=["rsi14", "macd"])
    _check_envelope(env, "signals_technical")
    assert set(env["data"]) >= {"symbol", "rsi14", "macd"}
    assert "sma200" not in env["data"]


async def test_sector_performance_top_n(monkeypatch):
    import opentrading_mcp.tools.scan as scan_mod

    rows = [{"Level": 1, "name": f"S{i}"} for i in range(10)]

    async def fake_rb(fn: Any, tool: str, timeout_secs: float = 45.0):
        return rows

    monkeypatch.setattr(scan_mod, "run_blocking", fake_rb)
    fn = _tool_fn("sector_performance", "scan")
    env = await fn(level=1, top_n=3)
    _check_envelope(env, "sector_performance")
    assert len(env["data"]["rows"]) == 3


async def test_money_flow_symbols(monkeypatch):
    from opentrading_mcp.providers import dnse as dnse_mod

    seen: dict[str, Any] = {}

    def fake_snap(symbols):
        seen["symbols"] = symbols
        return {"ok": True}

    monkeypatch.setattr(dnse_mod, "ws_snapshot", fake_snap)
    fn = _tool_fn("money_flow", "scan")
    env = await fn(symbols=["VCB"])
    _check_envelope(env, "money_flow")
    assert seen == {"symbols": ["VCB"]}


async def test_odds_limit_status_tag(monkeypatch):

    events = [
        {"title": "Fed cut", "status": "open", "tag": "fed", "volume24h": 5},
        {"title": "Fed hike", "status": "closed", "volume24h": 9},
        {"title": "Election", "status": "open", "tag": "politics", "volume24h": 7},
    ]

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any):
        return {"events": events}

    import opentrading_mcp.tools.intel as intel_mod

    monkeypatch.setattr(intel_mod, "_call", fake_call)
    fn = _tool_fn("world_prediction_odds", "intel")
    env = await fn(query=None, limit=1, tag="economics")
    _check_envelope(env, "world_prediction_odds")
    assert len(env["data"]["events"]) == 1


async def test_geo_limit(monkeypatch):

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any):
        return {"articles": [{"t": i} for i in range(10)]}

    import opentrading_mcp.tools.intel as intel_mod

    monkeypatch.setattr(intel_mod, "_call", fake_call)
    fn = _tool_fn("geo_intel", "intel")
    env = await fn(limit=4)
    _check_envelope(env, "geo_intel")
    assert len(env["data"]["articles"]) == 4


async def test_compare_equities_metrics(monkeypatch):
    import opentrading_mcp.tools.intel as intel_mod

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any):
        if tool == "o":
            return [{"close_price": 100.0, "extra": 1}]
        return [{"c": 100.0 + i} for i in range(30)]

    monkeypatch.setattr(intel_mod, "_call", fake_call)
    fn = _tool_fn("compare_equities", "intel")
    env = await fn(symbols=["VCB"], metrics=["momentum_1m_pct"])
    _check_envelope(env, "compare_equities")
    row = env["data"]["rows"][0]
    assert set(row) == {"symbol", "momentum_1m_pct"}


async def test_evidence_bundle_calc_ids():
    fn = _tool_fn("evidence_bundle", "intel")
    env = await fn(claim_ids=["c1"], calc_ids=["k1", "k2"])
    _check_envelope(env, "evidence_bundle")
    assert env["data"]["calc_ids"] == ["k1", "k2"]
    assert env["data"]["locked"] is True
