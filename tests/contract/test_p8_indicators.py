"""P8 contract: Ichimoku + swings/fibo + multi-TF + rsi strategy + month filter (TDD)."""

from __future__ import annotations

import math
from typing import Any


def _candles(prices: list[float]) -> list[dict[str, Any]]:
    rows = []
    for i, c in enumerate(prices):
        rows.append(
            {
                "t": f"2026-01-{(i % 28) + 1:02d}",
                "o": c - 0.1,
                "h": c + 0.3,
                "l": c - 0.3,
                "c": c,
                "v": 1000.0,
            }
        )
    return rows


def _trend(n: int = 80, drift: float = 0.4, amp: float = 2.0, period: int = 20) -> list[float]:
    return [20.0 + drift * i + amp * math.sin(2 * math.pi * i / period) for i in range(n)]


def test_ichimoku_bullish_on_uptrend():
    from opentrading_mcp.providers import technicals as tech_p

    out = tech_p.compute(_candles(_trend()))
    ich = out["ichimoku"]
    assert ich["tenkan"] is not None and ich["kijun"] is not None
    assert ich["tenkan"] > ich["kijun"]
    assert ich["signal"] == "bullish"


def test_ichimoku_bearish_on_downtrend():
    from opentrading_mcp.providers import technicals as tech_p

    out = tech_p.compute(
        _candles(
            [-x for x in _trend()]
            if False
            else [60.0 - 0.4 * i + 2.0 * math.sin(i) for i in range(80)]
        )
    )
    assert out["ichimoku"]["signal"] == "bearish"


def test_ichimoku_needs_bars():
    from opentrading_mcp.providers import technicals as tech_p

    out = tech_p.compute(_candles([20.0 + 0.1 * i for i in range(15)]))
    assert out["ichimoku"]["senkou_b"] is None
    assert out["ichimoku"]["signal"] is None


def test_swing_trend_higher_high():
    from opentrading_mcp.providers import technicals as tech_p

    out = tech_p.compute(_candles(_trend(n=120)))
    assert out["swing_trend"] == "higher-high"
    assert len(out["swings"]) >= 4
    assert {s["side"] for s in out["swings"]} <= {"HH", "HL", "LH", "LL"}


def test_swing_trend_lower_low():
    from opentrading_mcp.providers import technicals as tech_p

    prices = [60.0 - 0.4 * i + 2.0 * math.sin(2 * math.pi * i / 20) for i in range(120)]
    out = tech_p.compute(_candles(prices))
    assert out["swing_trend"] == "lower-low"


def test_fib_levels_ordered():
    from opentrading_mcp.providers import technicals as tech_p

    out = tech_p.compute(_candles(_trend(n=120)))
    fib = out["fib"]
    assert fib["direction"] == "up"
    lv = fib["levels"]
    assert lv["0.0"] < lv["0.618"] < lv["1.0"]
    lo, hi = lv["0.0"], lv["1.0"]
    assert abs(lv["0.5"] - (lo + hi) / 2) < 1e-6


async def test_signals_technical_weekly(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p
    from opentrading_mcp.server import create_server, register_preset

    server = create_server("scan")
    register_preset(server, "scan")
    fn = server._tool_manager.get_tool("signals_technical").fn
    weeklies = _candles(_trend(n=60))

    def fake_history(symbol: str, days: int = 365, interval: str = "1D"):
        assert interval == "1W"
        return list(weeklies)

    monkeypatch.setattr(vn_p, "quote_history", fake_history)
    env = await fn(symbol="VCB", interval="1W")
    assert env["availability"] == "available"
    assert env["data"]["interval"] == "1W"
    assert not any("daily-only" in w for w in env.get("warnings", []))
    assert env["data"]["rsi14"] is not None


async def test_signals_technical_bad_interval():
    from opentrading_mcp.server import create_server, register_preset

    server = create_server("scan")
    register_preset(server, "scan")
    fn = server._tool_manager.get_tool("signals_technical").fn
    env = await fn(symbol="VCB", interval="1H")
    assert env["availability"] == "unavailable"


def _v_shape() -> list[float]:
    down = [40.0 - 0.8 * i for i in range(25)]
    up = [down[-1] + 1.0 * i for i in range(1, 26)]
    return down + up


async def test_rsi_meanrev_trades(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p
    from opentrading_mcp.server import create_server, register_preset

    server = create_server("quant")
    register_preset(server, "quant")
    fn = server._tool_manager.get_tool("backtest_strategies").fn
    candles = _candles(_v_shape())

    def fake_history(symbol: str, days: int = 365):
        return list(candles)

    monkeypatch.setattr(vn_p, "quote_history", fake_history)
    env = await fn(symbol="VCB", strategy="rsi_meanrev")
    assert env["availability"] == "available"
    assert env["data"]["trades"] >= 1


async def test_months_filter_blocks_all(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p
    from opentrading_mcp.server import create_server, register_preset

    server = create_server("quant")
    register_preset(server, "quant")
    fn = server._tool_manager.get_tool("backtest_strategies").fn
    rows = []
    for i, c in enumerate(_v_shape()):
        rows.append(
            {
                "t": f"2026-03-{(i % 28) + 1:02d}",
                "o": c - 0.1,
                "h": c + 0.3,
                "l": c - 0.3,
                "c": c,
                "v": 1000.0,
            }
        )

    def fake_history(symbol: str, days: int = 365):
        return list(rows)

    monkeypatch.setattr(vn_p, "quote_history", fake_history)
    env = await fn(symbol="VCB", strategy="rsi_meanrev", months=[1])
    assert env["data"]["trades"] == 0
    assert any("month" in str(w).lower() for w in env.get("warnings", []))
