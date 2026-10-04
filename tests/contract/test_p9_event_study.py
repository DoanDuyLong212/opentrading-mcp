"""P2.2 contract: event_study abnormal returns around event dates (TDD)."""

from __future__ import annotations

from typing import Any


def _dated_candles(prices: list[float], start_day: int = 1) -> list[dict[str, Any]]:
    rows = []
    for i, c in enumerate(prices):
        rows.append(
            {
                "t": f"2026-01-{(start_day + i - 1) % 28 + 1:02d}",
                "o": c - 0.1,
                "h": c + 0.3,
                "l": c - 0.3,
                "c": c,
                "v": 1000.0,
            }
        )
    return rows


def _tool_fn(name: str):
    from opentrading_mcp.server import create_server, register_preset

    server = create_server("quant")
    register_preset(server, "quant")
    tool = server._tool_manager.get_tool(name)
    assert tool is not None, f"tool {name} not registered"
    return tool.fn


async def test_event_study_positive_jump(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    # flat 20 -> +10% jump on 2026-01-21 -> flat 10; benchmark flat
    prices = [20.0] * 20 + [22.0] * 11
    bench = [1700.0] * 31

    def fake_history(symbol: str, days: int = 365):
        if symbol == "VNINDEX":
            return _dated_candles(bench)
        return _dated_candles(prices)

    monkeypatch.setattr(vn_p, "quote_history", fake_history)
    env = await _tool_fn("event_study")(
        symbol="VCB", dates=["2026-01-21"], window_before=5, window_after=5
    )
    assert env["availability"] == "available"
    d = env["data"]
    assert d["events"] == 1
    assert d["avg_car_pct"] > 5.0
    assert d["rows"][0]["car_pct"] > 5.0


async def test_event_study_missing_date_skipped(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    prices = [20.0] * 31

    def fake_history(symbol: str, days: int = 365):
        return _dated_candles(prices)

    monkeypatch.setattr(vn_p, "quote_history", fake_history)
    env = await _tool_fn("event_study")(symbol="VCB", dates=["2025-06-15"])
    d = env["data"]
    assert d["events"] == 0
    assert "skipped" in d and d["skipped"] == 1


async def test_event_study_needs_dates():
    env = await _tool_fn("event_study")(symbol="VCB", dates=[])
    assert env["availability"] == "empty"
