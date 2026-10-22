"""alert_check evaluates every rule; the screener says what it screened.

Live on 2026-10-23: three rules went in and two were evaluated (a second rule
for FPT replaced the first), "HPG above 999999" fired because an unknown op
fell through to "<", and rsi14 from 30 candles read 26.14 while
signals_technical said 32.16 for the same symbol at the same time.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from opentrading_mcp.server import create_server, register_preset


def _tool(name: str):
    server = create_server("scan")
    register_preset(server, "scan")
    tool = server._tool_manager.get_tool(name)
    assert tool is not None
    return tool.fn


def _candles(n: int) -> list[dict[str, Any]]:
    out, price = [], 100.0
    for i in range(n):
        price += 1.0 if i % 3 else -1.6
        out.append({"t": f"2026-{(i // 28) % 12 + 1:02d}-{i % 28 + 1:02d}", "o": price,
                    "h": price + 0.5, "l": price - 0.5, "c": price, "v": 1000.0 + i})
    return out


@pytest.fixture()
def board(monkeypatch):
    from opentrading_mcp.providers import store
    from opentrading_mcp.providers import vnstock as vn_p

    monkeypatch.setattr(store, "_memory", {})
    seen: dict[str, list[int]] = {"days": []}
    quotes = {"FPT": 57400.0, "HPG": 21250.0}

    def fake_batch(symbols: list[str]) -> list[dict[str, Any]]:
        return [{"symbol": s, "close_price": quotes[s]} for s in symbols if s in quotes]

    def fake_history(symbol: str, days: int = 365, interval: str = "1D"):
        seen["days"].append(days)
        return _candles(days)

    monkeypatch.setattr(vn_p, "equity_quote_batch", fake_batch)
    monkeypatch.setattr(vn_p, "quote_history", fake_history)
    return seen


async def test_every_rule_for_a_symbol_is_evaluated(board):
    env = await _tool("alert_check")(
        [
            {"symbol": "FPT", "metric": "price", "op": ">", "threshold": 1},
            {"symbol": "FPT", "metric": "rsi14", "op": "<", "threshold": 99},
        ]
    )
    data = env["data"]
    assert data["rules_evaluated"] == 2
    assert [(t["metric"], t["op"]) for t in data["triggered"]] == [("price", ">"), ("rsi14", "<")]
    assert data["triggered"][0]["price"] == 57400.0
    assert "price" not in data["triggered"][1]  # an RSI is not a price
    assert data["triggered"][1]["value"] < 99


async def test_unknown_op_is_skipped_not_read_as_less_than(board):
    env = await _tool("alert_check")(
        [
            {"symbol": "HPG", "metric": "price", "op": "above", "threshold": 999999},
            {"symbol": "HPG", "metric": "volume", "op": ">", "threshold": 1},
        ]
    )
    assert env["data"]["triggered"] == []
    assert any("unknown op 'above'" in w for w in env["warnings"])
    assert any("unknown metric 'volume'" in w for w in env["warnings"])


async def test_two_cross_rules_on_one_symbol_see_the_previous_state(board):
    from opentrading_mcp.providers import store

    store.cache_set("mcp:scan:alert_state", {"FPT:price": 49000.0}, ttl_seconds=60)
    env = await _tool("alert_check")(
        [
            {"symbol": "FPT", "metric": "price", "op": "cross_up", "threshold": 50000},
            {"symbol": "FPT", "metric": "price", "op": "cross_up", "threshold": 55000},
        ]
    )
    assert [t["threshold"] for t in env["data"]["triggered"]] == [50000.0, 55000.0]
    raw = await store.acache_get("mcp:scan:alert_state")
    state = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    assert state["FPT:price"] == 57400.0


async def test_rsi_matches_signals_technical(board):
    alert = await _tool("alert_check")(
        [{"symbol": "FPT", "metric": "rsi14", "op": ">", "threshold": 0}]
    )
    tech = await _tool("signals_technical")(symbol="FPT", interval="1D")
    assert board["days"][0] == board["days"][1] == 250
    assert alert["data"]["triggered"][0]["value"] == tech["data"]["rsi14"]


async def test_screener_reports_scope_and_fundamentals_period(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    universe = [{"symbol": f"S{i:02d}", "name": f"Co {i}"} for i in range(40)]
    monkeypatch.setattr(vn_p, "listing_symbols", lambda: [dict(r) for r in universe])

    def fake_fund(symbol: str, period: str = "year") -> dict[str, Any]:
        return {"symbol": symbol, "pe": 8.0, "roe": 0.2, "period_label": "2025"}

    monkeypatch.setattr(vn_p, "equity_fundamentals", fake_fund)
    env = await _tool("stock_screener")(max_pe=10, limit=5)
    data = env["data"]
    assert data["universe"] == 40
    assert data["screened"] == 20
    assert data["candidates"][0]["fundamentals_period"] == "2025"
    assert any("first 20 of 40" in w for w in env["warnings"])
    assert env["availability"] != "partial"  # every looked-up symbol was enriched
