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
            {"symbol": "HPG", "op": ">"},
        ]
    )
    assert env["data"]["triggered"] == []
    assert any("rule 2: needs symbol and threshold" in w for w in env["warnings"])
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
    assert data["coverage"] == {
        "stage": "fundamentals",
        "eligible": 40,
        "attempted": 20,
        "evaluated": 20,
    }
    assert data["candidates"][0]["fundamentals_period"] == "2025"
    assert any("first 20 of 40" in w for w in env["warnings"])
    assert env["availability"] != "partial"  # every looked-up symbol was enriched


async def test_screener_evaluated_excludes_missing_required_metric(monkeypatch):
    # A symbol carrying roe but not pe was "enriched", yet the pe filter can
    # never conclude on it: evaluated must not count it, and the warning must
    # name the symbol and the missing metric.
    from opentrading_mcp.providers import vnstock as vn_p

    universe = [{"symbol": f"S{i:02d}", "name": f"Co {i}"} for i in range(40)]
    monkeypatch.setattr(vn_p, "listing_symbols", lambda: [dict(r) for r in universe])
    no_pe = {f"S{i:02d}" for i in range(5)}

    def fake_fund(symbol: str, period: str = "year") -> dict[str, Any]:
        if symbol in no_pe:
            return {"symbol": symbol, "roe": 0.2, "period_label": "2025"}
        return {"symbol": symbol, "pe": 8.0, "roe": 0.2, "period_label": "2025"}

    monkeypatch.setattr(vn_p, "equity_fundamentals", fake_fund)
    env = await _tool("stock_screener")(max_pe=10, limit=5)
    data = env["data"]
    assert data["coverage"] == {
        "stage": "fundamentals",
        "eligible": 40,
        "attempted": 20,
        "evaluated": 15,  # S00-S04 lack pe, the exact metric the filter needs
    }
    assert any("S00" in w and "pe" in w for w in env["warnings"])
    assert env["availability"] == "partial"
    assert all(c["symbol"] not in no_pe for c in data["candidates"])


def _rising_history_sync(days: int) -> list[dict[str, Any]]:
    return [
        {"t": f"2026-{(d // 28) % 12 + 1:02d}-{d % 28 + 1:02d}", "o": 10.0, "h": 10.5,
         "l": 9.5, "c": 10.0 + d, "v": 1000.0}
        for d in range(days)
    ]


def _falling_history_sync(days: int) -> list[dict[str, Any]]:
    return [
        {"t": f"2026-{(d // 28) % 12 + 1:02d}-{d % 28 + 1:02d}", "o": 10.0, "h": 10.5,
         "l": 9.5, "c": 100.0 - d, "v": 1000.0}
        for d in range(days)
    ]


async def test_screener_technical_stage_reports_true_scope(monkeypatch):
    # Regression (23/10 review): 40 symbols + technical + limit=5 used to report
    # screened=40 while only 5 candidates were ever technically evaluated.
    from opentrading_mcp.providers import store
    from opentrading_mcp.providers import vnstock as vn_p

    monkeypatch.setattr(store, "_memory", {})
    monkeypatch.setattr(
        vn_p, "listing_symbols", lambda: [{"symbol": f"S{i:02d}"} for i in range(40)]
    )
    monkeypatch.setattr(vn_p, "equity_fundamentals", lambda symbol: {"pe": 8.0, "roe": 0.2})
    calls: list[str] = []

    def fake_history(symbol: str, days: int) -> list[dict[str, Any]]:
        calls.append(symbol)
        return _rising_history_sync(days)

    monkeypatch.setattr(vn_p, "quote_history", fake_history)
    env = await _tool("stock_screener")(technical={"above_sma20": True}, limit=5)
    data = env["data"]
    assert len(calls) == 5  # history is only called for the technical shortlist
    assert data["screened"] == 5
    assert data["universe"] == 40
    assert data["coverage"] == {
        "stage": "technical",
        "eligible": 40,
        "attempted": 5,
        "evaluated": 5,
    }
    assert any("first 5 of 40" in w for w in env["warnings"])
    assert env["availability"] != "partial"  # the cap is disclosed, not a data gap


async def test_screener_technical_unavailable_is_not_a_reject(monkeypatch):
    from opentrading_mcp.providers import store
    from opentrading_mcp.providers import vnstock as vn_p

    monkeypatch.setattr(store, "_memory", {})
    monkeypatch.setattr(
        vn_p, "listing_symbols", lambda: [{"symbol": f"S{i:02d}"} for i in range(5)]
    )
    monkeypatch.setattr(vn_p, "equity_fundamentals", lambda symbol: {"pe": 8.0, "roe": 0.2})

    def fake_history(symbol: str, days: int) -> list[dict[str, Any]]:
        if symbol == "S03":
            raise RuntimeError("history down")
        return _rising_history_sync(days)

    monkeypatch.setattr(vn_p, "quote_history", fake_history)
    env = await _tool("stock_screener")(technical={"above_sma20": True}, limit=5)
    data = env["data"]
    assert data["coverage"] == {
        "stage": "technical",
        "eligible": 5,
        "attempted": 5,
        "evaluated": 4,
    }
    assert data["screened"] == 5
    assert len(data["candidates"]) == 4  # the 4 evaluated-and-passing symbols
    assert env["availability"] == "partial"
    assert any("S03" in w for w in env["warnings"])

    # A required indicator the source cannot produce is unavailable too.
    import opentrading_mcp.providers.technicals as tech_mod

    monkeypatch.setattr(store, "_memory", {})
    monkeypatch.setattr(
        tech_mod, "compute", lambda candles: {"rsi14": None, "sma20": None, "last": 10.0}
    )
    env2 = await _tool("stock_screener")(technical={"above_sma20": True}, limit=5)
    assert env2["data"]["coverage"]["evaluated"] == 0
    assert env2["availability"] == "partial"
    assert any("sma20" in w for w in env2["warnings"])


async def test_screener_technical_eligible_follows_prefilter(monkeypatch):
    # eligible for the technical stage comes from the surviving candidates,
    # not from the universe.
    from opentrading_mcp.providers import store
    from opentrading_mcp.providers import vnstock as vn_p

    monkeypatch.setattr(store, "_memory", {})
    monkeypatch.setattr(
        vn_p, "listing_symbols", lambda: [{"symbol": f"S{i:02d}"} for i in range(40)]
    )
    monkeypatch.setattr(
        vn_p,
        "equity_fundamentals",
        lambda symbol: {"pe": 8.0 if int(symbol[1:]) < 10 else 30.0, "roe": 0.2},
    )
    calls: list[str] = []

    def fake_history(symbol: str, days: int) -> list[dict[str, Any]]:
        calls.append(symbol)
        return _rising_history_sync(days)

    monkeypatch.setattr(vn_p, "quote_history", fake_history)
    env = await _tool("stock_screener")(
        filters={"pe": [None, 20]}, technical={"above_sma20": True}, limit=5
    )
    data = env["data"]
    assert data["coverage"] == {
        "stage": "technical",
        "eligible": 10,  # only S00..S09 survive the pe filter
        "attempted": 5,
        "evaluated": 5,
    }
    assert len(calls) == 5
    assert [c["symbol"] for c in data["candidates"]] == [f"S{i:02d}" for i in range(5)]


async def test_screener_technical_empty_dict_is_no_technical_stage(monkeypatch):
    from opentrading_mcp.providers import store
    from opentrading_mcp.providers import vnstock as vn_p

    monkeypatch.setattr(store, "_memory", {})
    monkeypatch.setattr(
        vn_p, "listing_symbols", lambda: [{"symbol": f"S{i:02d}"} for i in range(40)]
    )
    monkeypatch.setattr(vn_p, "equity_fundamentals", lambda symbol: {"pe": 8.0, "roe": 0.2})
    calls: list[str] = []

    def fake_history(symbol: str, days: int) -> list[dict[str, Any]]:
        calls.append(symbol)
        return _rising_history_sync(days)

    monkeypatch.setattr(vn_p, "quote_history", fake_history)
    fn = _tool("stock_screener")
    env_none = await fn(technical=None, limit=5)
    assert calls == []  # no technical stage: no history calls at all
    assert env_none["data"]["coverage"] == {
        "stage": "local",
        "eligible": 40,
        "attempted": 40,
        "evaluated": 40,
    }
    assert env_none["data"]["screened"] == 40
    monkeypatch.setattr(store, "_memory", {})
    calls.clear()
    env_empty = await fn(technical={}, limit=5)
    assert calls == []  # {} normalizes to "no technical stage", not to a rule set
    assert env_empty["data"]["coverage"] == env_none["data"]["coverage"]
    assert env_empty["data"]["screened"] == 40


async def test_screener_all_technical_rejects_is_not_partial(monkeypatch):
    from opentrading_mcp.providers import store
    from opentrading_mcp.providers import vnstock as vn_p

    monkeypatch.setattr(store, "_memory", {})
    monkeypatch.setattr(
        vn_p, "listing_symbols", lambda: [{"symbol": f"S{i:02d}"} for i in range(5)]
    )
    monkeypatch.setattr(vn_p, "equity_fundamentals", lambda symbol: {"pe": 8.0, "roe": 0.2})
    monkeypatch.setattr(vn_p, "quote_history", lambda symbol, days: _falling_history_sync(days))
    env = await _tool("stock_screener")(technical={"above_sma20": True}, limit=5)
    data = env["data"]
    assert data["coverage"] == {
        "stage": "technical",
        "eligible": 5,
        "attempted": 5,
        "evaluated": 5,  # every candidate got a real pass/reject verdict
    }
    assert data["candidates"] == []
    assert env["availability"] != "partial"  # clean rejects are not a data gap
    assert not any("unavailable" in w for w in env["warnings"])


async def test_screener_valuation_coverage_survives_cache_hit(monkeypatch):
    from opentrading_mcp.providers import store
    from opentrading_mcp.providers import vnstock as vn_p

    monkeypatch.setattr(store, "_memory", {})
    monkeypatch.setattr(
        vn_p, "listing_symbols", lambda: [{"symbol": f"S{i:02d}"} for i in range(40)]
    )
    fund_calls: list[str] = []

    def fake_fund(symbol: str, period: str = "year") -> dict[str, Any]:
        fund_calls.append(symbol)
        return {"pe": 8.0, "roe": 0.2, "period_label": "2025"}

    monkeypatch.setattr(vn_p, "equity_fundamentals", fake_fund)
    fn = _tool("stock_screener")
    env = await fn(max_pe=10, limit=5)
    assert env["data"]["screened"] == 20
    assert env["data"]["coverage"] == {
        "stage": "fundamentals",
        "eligible": 40,
        "attempted": 20,
        "evaluated": 20,
    }
    assert len(fund_calls) == 20
    env2 = await fn(max_pe=10, limit=5)
    assert env2["provenance"]["cached"] is True
    assert env2["data"]["coverage"] == env["data"]["coverage"]
    assert env2["data"]["screened"] == 20
    assert any("first 20 of 40" in w for w in env2["warnings"])
    assert env2["availability"] == env["availability"]


async def test_screener_fundamentals_failure_warns_per_symbol(monkeypatch):
    from opentrading_mcp.providers import store
    from opentrading_mcp.providers import vnstock as vn_p

    monkeypatch.setattr(store, "_memory", {})
    monkeypatch.setattr(
        vn_p, "listing_symbols", lambda: [{"symbol": f"S{i:02d}"} for i in range(3)]
    )

    def fake_fund(symbol: str, period: str = "year") -> dict[str, Any]:
        if symbol == "S01":
            raise RuntimeError("upstream down")
        return {"pe": 8.0, "roe": 0.2}

    monkeypatch.setattr(vn_p, "equity_fundamentals", fake_fund)
    env = await _tool("stock_screener")(max_pe=10, limit=5)
    data = env["data"]
    assert data["coverage"] == {
        "stage": "fundamentals",
        "eligible": 3,
        "attempted": 3,
        "evaluated": 2,
    }
    assert env["availability"] == "partial"
    assert any("S01" in w for w in env["warnings"])
    assert len(data["candidates"]) == 2
