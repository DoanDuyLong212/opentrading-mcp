"""P3 contract: full technicals pandas + signals_technical (TDD)."""

from __future__ import annotations

import inspect
from typing import Any


def _scan_tool_fn(name: str):
    from opentrading_mcp.server import create_server, register_preset

    server = create_server("scan")
    register_preset(server, "scan")
    tool = server._tool_manager.get_tool(name)
    assert tool is not None, f"tool {name} not registered"
    return tool.fn


def _check_envelope(env: dict[str, Any], tool: str) -> None:
    for key in ("data", "provenance", "warnings", "availability"):
        assert key in env, f"{tool}: envelope missing {key!r}"
    assert env["provenance"]["timezone"] == "Asia/Ho_Chi_Minh"
    assert env["availability"] in {"available", "empty", "stale", "partial", "unavailable"}


def _make_candles(n: int, start: float = 20.0, step: float = 0.3) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i in range(n):
        c = start + i * step
        rows.append(
            {
                "t": f"2026-06-{i % 28 + 1:02d}",
                "o": c - 0.1,
                "h": c + 0.3,
                "l": c - 0.3,
                "c": c,
                "v": 1000.0 + i * 10.0,
            }
        )
    return rows


def test_compute_rsi_wilder_range_clamp():
    from opentrading_mcp.providers import technicals as t

    assert hasattr(t, "compute")
    candles = _make_candles(60)
    out = t.compute(candles)
    assert "rsi14" in out
    rsi = out["rsi14"]
    assert isinstance(rsi, float)
    assert 0.0 <= rsi <= 100.0, f"RSI out of range: {rsi}"
    # strong uptrend -> RSI elevated (Wilder)
    assert rsi > 55.0, f"uptrend RSI should be >55, got {rsi}"

    # strong downtrend -> RSI depressed
    down = _make_candles(60, start=80.0, step=-0.4)
    out2 = t.compute(down)
    assert 0.0 <= out2["rsi14"] <= 100.0
    assert out2["rsi14"] < 45.0, f"downtrend RSI should be <45, got {out2['rsi14']}"


def test_compute_macd_shape():
    from opentrading_mcp.providers import technicals as t

    out = t.compute(_make_candles(60))
    assert "macd" in out
    macd = out["macd"]
    assert set(macd.keys()) >= {"line", "signal", "hist"}
    for k in ("line", "signal", "hist"):
        assert isinstance(macd[k], float), f"macd.{k} not float"
    # hist == line - signal (within float tolerance)
    assert abs(macd["hist"] - (macd["line"] - macd["signal"])) < 1e-6


def test_compute_all_keys_present():
    from opentrading_mcp.providers import technicals as t

    out = t.compute(_make_candles(100))
    for key in (
        "rsi14",
        "stoch_k",
        "stoch_d",
        "cci20",
        "adx14",
        "macd",
        "momentum10",
        "ao",
        "ema10",
        "ema20",
        "ema50",
        "sma10",
        "sma20",
        "sma50",
        "sma200",
        "vwma",
        "hull9",
        "boll_upper",
        "boll_lower",
        "atr14",
        "recommend",
    ):
        assert key in out, f"compute missing {key!r}"


def test_compute_vwma_fallback_no_volume():
    from opentrading_mcp.providers import technicals as t

    candles = _make_candles(60)
    for row in candles:
        row.pop("v", None)
    out = t.compute(candles)
    assert "vwma" in out and "sma20" in out
    assert isinstance(out["vwma"], float)
    # fallback to sma when volume missing
    assert abs(out["vwma"] - out["sma20"]) < 1e-6


def test_recommend_enum():
    from opentrading_mcp.providers import technicals as t

    up = t.compute(_make_candles(100, step=0.3))
    assert up["recommend"] in {"Buy", "Sell", "Neutral"}
    down = t.compute(_make_candles(100, start=80.0, step=-0.4))
    assert down["recommend"] in {"Buy", "Sell", "Neutral"}
    # directional sanity: uptrend should not recommend Sell, downtrend not Buy
    assert up["recommend"] in {"Buy", "Neutral"}
    assert down["recommend"] in {"Sell", "Neutral"}


async def test_signals_technical_gate_len_lt_30_empty(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    monkeypatch.setattr(vn_p, "quote_history", lambda *a, **k: _make_candles(10))
    fn = _scan_tool_fn("signals_technical")
    env = await fn(symbol="VCB")
    _check_envelope(env, "signals_technical")
    assert env["availability"] == "empty"


async def test_signals_technical_full_envelope(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    monkeypatch.setattr(vn_p, "quote_history", lambda *a, **k: _make_candles(100))
    fn = _scan_tool_fn("signals_technical")
    # backward-compat: callable with only symbol
    env = await fn(symbol="VCB")
    _check_envelope(env, "signals_technical")
    assert env["provenance"]["source"] == "computed-local"
    data = env["data"]
    assert data["symbol"] == "VCB"
    assert data["recommend"] in {"Buy", "Sell", "Neutral"}
    assert 0.0 <= data["rsi14"] <= 100.0
    assert "macd" in data and "hist" in data["macd"]
    # interval param exists with default 1D
    sig = inspect.signature(fn)
    assert "interval" in sig.parameters
    assert sig.parameters["interval"].default == "1D"
    env2 = await fn(symbol="VCB", interval="1D")
    _check_envelope(env2, "signals_technical")
