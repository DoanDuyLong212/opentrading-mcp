"""P6 contract: batch cap 100, market_overview, technical patterns (TDD RED)."""

from __future__ import annotations

from typing import Any

from opentrading_mcp.server import create_server, register_preset


def _tool_fn(name: str, preset: str = "market"):
    server = create_server(preset)
    register_preset(server, preset)
    tool = server._tool_manager.get_tool(name)
    assert tool is not None, f"tool {name} not registered"
    return tool.fn


def _check_envelope(env: dict[str, Any], tool: str) -> None:
    for key in ("data", "provenance", "warnings", "availability"):
        assert key in env, f"{tool}: envelope missing {key!r}"


async def test_candles_batch_caps_at_100(monkeypatch):
    import opentrading_mcp.tools.market as market_mod

    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return [{"t": "2026-01-02", "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": 1.0}]

    monkeypatch.setattr(market_mod, "run_blocking", fake_block)
    fn = _tool_fn("market_candles_batch")
    env = await fn(symbols=[f"S{i}" for i in range(105)], days=5, summary=True)
    _check_envelope(env, "market_candles_batch")
    assert len(env["data"]["series"]) == 100
    assert any("100" in w for w in env["warnings"])


async def test_market_overview_composite(monkeypatch):
    import opentrading_mcp.tools.market as market_mod
    from opentrading_mcp.providers import dnse as dnse_p
    from opentrading_mcp.providers import vietstock as vs_p
    from opentrading_mcp.providers import vnstock as vn_p

    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        target = getattr(fn, "func", None)
        if target is vn_p.equity_quote_batch:
            return [
                {"symbol": "VCB", "change": 1.5},
                {"symbol": "HPG", "change": -0.5},
                {"symbol": "SSI", "change": 0.0},
            ]
        if target is vs_p.market_price:
            return [
                {"symbol": "VCB", "change": 1.5},
                {"symbol": "HPG", "change": -0.5},
            ]
        # P02: the dnse ws_snapshot leg is offloaded through run_blocking too
        if target is dnse_p.ws_snapshot or callable(target):
            return {"mock": True}
        raise AssertionError(f"unexpected upstream {target}")

    monkeypatch.setattr(market_mod, "run_blocking", fake_block)
    monkeypatch.setattr(dnse_p, "ws_snapshot", lambda symbols: {"mock": True})
    fn = _tool_fn("market_overview")
    env = await fn()
    _check_envelope(env, "market_overview")
    data = env["data"]
    assert data["breadth"] == {"advancers": 1, "decliners": 1, "flat": 1}
    assert data["movers"][0]["symbol"] == "VCB"
    assert data["session"] == {"mock": True}


def test_compute_detects_hammer_and_levels():
    from opentrading_mcp.providers import technicals as tech_p

    candles = [
        {"t": f"2026-01-{d:02d}", "o": 10.0, "h": 10.2, "l": 9.8, "c": c, "v": 100.0}
        for d, c in zip(range(1, 31), [10.0] * 29 + [10.0], strict=True)
    ]
    candles[-1] = {"t": "2026-01-30", "o": 10.1, "h": 10.12, "l": 9.5, "c": 10.05, "v": 200.0}
    out = tech_p.compute(candles)
    assert "hammer" in out["patterns"]
    assert out["support"] <= 9.5
    assert out["resistance"] >= 10.2


def test_compute_detects_bullish_engulfing():
    from opentrading_mcp.providers import technicals as tech_p

    base = [
        {"t": f"2026-01-{d:02d}", "o": 10.0, "h": 10.1, "l": 9.9, "c": 10.0, "v": 100.0}
        for d in range(1, 29)
    ]
    base.append({"t": "2026-01-29", "o": 10.0, "h": 10.0, "l": 9.7, "c": 9.8, "v": 100.0})
    base.append({"t": "2026-01-30", "o": 9.7, "h": 10.2, "l": 9.7, "c": 10.1, "v": 200.0})
    out = tech_p.compute(base)
    assert "engulfing_bull" in out["patterns"]


async def test_technical_indicators_filter_keeps_patterns(monkeypatch):
    import opentrading_mcp.tools.scan as scan_mod

    rows = [
        {"t": f"2026-01-{d:02d}", "o": 10.0, "h": 10.2, "l": 9.8, "c": 10.0, "v": 100.0}
        for d in range(1, 61)
    ]

    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return rows

    monkeypatch.setattr(scan_mod, "run_blocking", fake_block)
    server = create_server("scan")
    register_preset(server, "scan")
    tool = server._tool_manager.get_tool("signals_technical")
    assert tool is not None
    env = await tool.fn(symbol="VCB", indicators=["patterns", "support"])
    assert set(env["data"]) >= {"symbol", "interval", "patterns", "support"}
