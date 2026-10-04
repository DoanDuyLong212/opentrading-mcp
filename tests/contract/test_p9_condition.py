"""P2.3 contract: condition_asset gate in backtest engine (TDD)."""

from __future__ import annotations

from typing import Any


def _candles(prices: list[float]) -> list[dict[str, Any]]:
    import datetime

    base = datetime.date(2026, 1, 5)
    rows = []
    for i, c in enumerate(prices):
        d = base + datetime.timedelta(days=i)
        rows.append(
            {"t": d.isoformat(), "o": c - 0.1, "h": c + 0.3, "l": c - 0.3, "c": c, "v": 1000.0}
        )
    return rows


def _tool_fn(name: str):
    from opentrading_mcp.server import create_server, register_preset

    server = create_server("quant")
    register_preset(server, "quant")
    tool = server._tool_manager.get_tool(name)
    assert tool is not None
    return tool.fn


def _v_shape() -> list[float]:
    down = [40.0 - 0.5 * i for i in range(40)]
    return down + [down[-1] + 0.6 * i for i in range(1, 41)]


async def test_condition_always_true_matches_baseline(monkeypatch):
    from opentrading_mcp.providers import vnstock as _vnp

    stock = _candles(_v_shape())
    rising = _candles([10.0 + 0.5 * i for i in range(80)])

    def fake_history(symbol: str, days: int = 365):
        return list(rising) if symbol == "COND" else list(stock)

    monkeypatch.setattr(_vnp, "quote_history", fake_history)
    fn = _tool_fn("backtest_strategies")
    base = await fn(symbol="VCB", strategy="sma_cross", fast=5, slow=20)
    cond = await fn(
        symbol="VCB",
        strategy="sma_cross",
        fast=5,
        slow=20,
        condition_symbol="COND",
    )
    assert base["data"]["trades"] == cond["data"]["trades"]
    assert base["data"]["net_return"] == cond["data"]["net_return"]


async def test_condition_always_false_blocks_all(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    stock = _candles(_v_shape())
    falling = _candles([50.0 - 0.5 * i for i in range(80)])

    def fake_history(symbol: str, days: int = 365):
        return list(falling) if symbol == "COND" else list(stock)

    monkeypatch.setattr(vn_p, "quote_history", fake_history)
    fn = _tool_fn("backtest_strategies")
    env = await fn(
        symbol="VCB",
        strategy="sma_cross",
        fast=5,
        slow=20,
        condition_symbol="COND",
    )
    assert env["data"]["trades"] == 0
    assert any("condition" in str(w).lower() for w in env.get("warnings", []))
