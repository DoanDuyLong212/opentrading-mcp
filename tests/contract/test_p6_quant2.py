"""P6 contract: quant2 tools (TDD RED). Pure-local math on candle closes."""

from __future__ import annotations

from typing import Any

from opentrading_mcp.server import create_server, register_preset


def _tool_fn(name: str, preset: str = "quant"):
    server = create_server(preset)
    register_preset(server, preset)
    tool = server._tool_manager.get_tool(name)
    assert tool is not None, f"tool {name} not registered"
    return tool.fn


def _check_envelope(env: dict[str, Any], tool: str) -> None:
    for key in ("data", "provenance", "warnings", "availability"):
        assert key in env, f"{tool}: envelope missing {key!r}"
    assert env["provenance"]["timezone"] == "Asia/Ho_Chi_Minh"


def _candles(closes: list[float], start: str = "2025-01-02") -> list[dict[str, Any]]:
    import datetime

    day = datetime.date.fromisoformat(start)
    out = []
    d = day
    for c in closes:
        while d.weekday() >= 5:
            d += datetime.timedelta(days=1)
        out.append({"t": d.isoformat(), "o": c, "h": c, "l": c, "c": c, "v": 1000.0})
        d += datetime.timedelta(days=1)
    return out


def test_run_strategy_buy_hold_profit():
    from opentrading_mcp.tools import quant_shared as qmod

    closes = [100.0 + i for i in range(40)]
    res = qmod._run_strategy(closes, "buy_hold", 5, 20, 0.0)
    assert res["trades"] == 1
    assert res["net_return"] > 0.35


def test_run_strategy_sma_cross_trades_twice():
    from opentrading_mcp.tools import quant_shared as qmod

    closes = [100.0] * 20 + [110.0] * 20 + [90.0] * 20 + [110.0] * 20
    res = qmod._run_strategy(closes, "sma_cross", 5, 20, 0.0)
    assert res["trades"] >= 2


async def test_correlation_identical_series_is_one(monkeypatch):
    import opentrading_mcp.tools.quant_stats as qmod

    series = _candles([100.0 + (i % 7) for i in range(60)])

    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return series

    monkeypatch.setattr(qmod, "run_blocking", fake_block)
    fn = _tool_fn("correlation_matrix")
    env = await fn(symbols=["AAA", "BBB"], days=60)
    _check_envelope(env, "correlation_matrix")
    assert env["data"]["matrix"]["AAA"]["BBB"] == 1.0


async def test_seasonality_buckets_twelve_months(monkeypatch):
    import datetime

    import opentrading_mcp.tools.quant_stats as qmod

    closes = [100.0 + i * 0.1 for i in range(260)]
    day = datetime.date(2025, 1, 2)
    rows, d = [], day
    for c in closes:
        while d.weekday() >= 5:
            d += datetime.timedelta(days=1)
        rows.append({"t": d.isoformat(), "o": c, "h": c, "l": c, "c": c, "v": 1.0})
        d += datetime.timedelta(days=1)

    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return rows

    monkeypatch.setattr(qmod, "run_blocking", fake_block)
    fn = _tool_fn("seasonality")
    env = await fn(symbol="AAA", window=21)
    _check_envelope(env, "seasonality")
    assert len(env["data"]["months"]) == 12
    assert "date_note" in env["data"]


async def test_backtest_strategies_unknown_is_unavailable():
    fn = _tool_fn("backtest_strategies")
    env = await fn(symbol="VCB", strategy="nope")
    assert env["availability"] == "unavailable"


async def test_portfolio_optimize_equal_weights_sum_one(monkeypatch):
    import opentrading_mcp.tools.quant_stats as qmod

    series = _candles([100.0 + (i % 5) for i in range(80)])

    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return series

    monkeypatch.setattr(qmod, "run_blocking", fake_block)
    fn = _tool_fn("portfolio_optimize")
    env = await fn(symbols=["AAA", "BBB", "CCC"], objective="equal")
    _check_envelope(env, "portfolio_optimize")
    weights = env["data"]["weights"]
    assert abs(sum(weights.values()) - 1.0) < 1e-9
    assert set(weights) == {"AAA", "BBB", "CCC"}


async def test_param_sweep_caps_combos(monkeypatch):
    import opentrading_mcp.tools.quant_backtest as qmod

    series = _candles([100.0 + (i % 9) for i in range(120)])

    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return series

    monkeypatch.setattr(qmod, "run_blocking", fake_block)
    fn = _tool_fn("param_sweep")
    env = await fn(symbol="AAA", fast_range=[2, 3, 4, 5, 6], slow_range=[10, 15, 20, 25, 30, 35])
    _check_envelope(env, "param_sweep")
    assert env["data"]["combos_evaluated"] <= 30
    assert len(env["data"]["ranked"]) == env["data"]["combos_evaluated"]
