"""P1 contract: summary + columns + missing for OHLCV tools (TDD)."""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from opentrading_mcp.server import create_server, register_preset

FAKE_CANDLES = [
    {"t": "2026-09-20", "o": 10.0, "h": 12.0, "l": 9.0, "c": 11.0, "v": 100.0},
    {"t": "2026-09-21", "o": 11.0, "h": 13.0, "l": 10.0, "c": 12.0, "v": 200.0},
    {"t": "2026-09-22", "o": 12.0, "h": 14.0, "l": 11.0, "c": 13.0, "v": 300.0},
]

FAKE_BARS = [
    {"time": "2026-09-20", "open": 10.0, "high": 12.0, "low": 9.0, "close": 11.0, "volume": 100.0},
    {"time": "2026-09-21", "open": 11.0, "high": 13.0, "low": 10.0, "close": 12.0, "volume": 200.0},
]


def _tool_fn(name: str):
    server = create_server("market")
    register_preset(server, "market")
    tool = server._tool_manager.get_tool(name)
    assert tool is not None, f"tool {name} not registered"
    return tool.fn


def _check_envelope(env: dict[str, Any], tool: str) -> None:
    for key in ("data", "provenance", "warnings", "availability"):
        assert key in env, f"{tool}: envelope missing {key!r}"
    assert env["provenance"]["timezone"] == "Asia/Ho_Chi_Minh"
    assert env["availability"] in {"available", "empty", "stale", "partial", "unavailable"}


async def test_vn_quote_history_summary_shape(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    monkeypatch.setattr(vn_p, "quote_history", lambda *a, **k: list(FAKE_CANDLES))
    fn = _tool_fn("vn_quote_history")
    env = await fn(symbol="VCB", days=5, summary=True)
    _check_envelope(env, "vn_quote_history")
    data = env["data"]
    assert data["symbol"] == "VCB"
    assert data["count"] == 3
    assert "last" in data and "high" in data and "low" in data
    assert "candles" not in data and "bars" not in data


async def test_vn_quote_history_columns_projection(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    monkeypatch.setattr(vn_p, "quote_history", lambda *a, **k: list(FAKE_CANDLES))
    fn = _tool_fn("vn_quote_history")
    env = await fn(symbol="VCB", days=5, columns=["t", "c"])
    data = env["data"]
    assert "candles" in data
    assert len(data["candles"]) == 3
    for row in data["candles"]:
        assert set(row.keys()) == {"t", "c"}


@pytest.mark.parametrize(
    "tool_name,provider_fn",
    [
        ("vn_index_ohlcv", "index_ohlcv"),
        ("vn_equity_ohlcv", "equity_ohlcv"),
        ("vn_futures_ohlcv", "futures_ohlcv"),
    ],
)
async def test_vn_ext_summary_and_columns(monkeypatch, tool_name, provider_fn):
    from opentrading_mcp.providers import vnstock as vn_p

    monkeypatch.setattr(vn_p, provider_fn, lambda *a, **k: list(FAKE_BARS))
    fn = _tool_fn(tool_name)
    env = await fn(symbol="X", count=5, summary=True)
    _check_envelope(env, tool_name)
    assert env["data"]["count"] == 2
    assert "last" in env["data"] and "high" in env["data"] and "low" in env["data"]
    assert "bars" not in env["data"]

    env2 = await fn(symbol="X", count=5, columns=["time", "close"])
    assert len(env2["data"]["bars"]) == 2
    for row in env2["data"]["bars"]:
        assert set(row.keys()) == {"time", "close"}


async def test_dnse_ohlc_history_defaults_and_summary_columns(monkeypatch):
    from opentrading_mcp.providers import dnse as dnse_p

    fn = _tool_fn("dnse_ohlc_history")
    sig = inspect.signature(fn)
    assert sig.parameters["bar_type"].default == "derivative"
    assert sig.parameters["from_date"].default == "2018-08-01"
    assert sig.parameters["summary"].default is False
    assert sig.parameters["columns"].default is None

    monkeypatch.setattr(dnse_p, "ohlc_history", lambda *a, **k: list(FAKE_CANDLES))
    env = await fn(symbol="VN30F1M", resolution=15, summary=True)
    _check_envelope(env, "dnse_ohlc_history")
    assert env["data"]["count"] == 3
    assert "bars" not in env["data"]

    env2 = await fn(symbol="VN30F1M", resolution=15, columns=["t", "c"])
    for row in env2["data"]["bars"]:
        assert set(row.keys()) == {"t", "c"}


async def test_market_candles_batch_missing_and_cap(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    def fake_history(symbol, days=30):
        if symbol == "BAD":
            from opentrading_mcp.providers.errors import ProviderUnavailable

            raise ProviderUnavailable("no candles for BAD")
        return list(FAKE_CANDLES)

    monkeypatch.setattr(vn_p, "quote_history", fake_history)
    fn = _tool_fn("market_candles_batch")
    env = await fn(symbols=["VCB", "BAD"], days=5)
    _check_envelope(env, "market_candles_batch")
    assert "series" in env["data"] and "missing" in env["data"]
    assert len(env["data"]["series"]) == 1
    assert len(env["data"]["missing"]) == 1
    assert env["data"]["missing"][0]["symbol"] == "BAD"
    assert "error" in env["data"]["missing"][0]
    assert env["availability"] == "partial"

    many = [f"S{i}" for i in range(55)]
    env2 = await fn(symbols=many, days=5)
    assert len(env2["data"]["series"]) + len(env2["data"]["missing"]) == 55
    huge = [f"S{i}" for i in range(105)]
    env3 = await fn(symbols=huge, days=5)
    assert len(env3["data"]["series"]) + len(env3["data"]["missing"]) == 100
    assert any("100" in w for w in env3["warnings"])


async def test_market_candles_batch_summary_no_candles(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    monkeypatch.setattr(vn_p, "quote_history", lambda *a, **k: list(FAKE_CANDLES))
    fn = _tool_fn("market_candles_batch")
    env = await fn(symbols=["VCB"], days=5, summary=True)
    _check_envelope(env, "market_candles_batch")
    assert len(env["data"]["series"]) == 1
    item = env["data"]["series"][0]
    assert "candles" not in item
    assert item["count"] == 3


async def test_vn_equity_quote_batch_columns(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    fake_quotes = [
        {"symbol": "VCB", "price": 10.0, "volume": 5},
        {"symbol": "HPG", "price": 20.0, "volume": 7},
    ]
    monkeypatch.setattr(vn_p, "equity_quote_batch", lambda *a, **k: list(fake_quotes))
    fn = _tool_fn("vn_equity_quote_batch")
    env = await fn(symbols=["VCB", "HPG"], columns=["symbol", "price"])
    _check_envelope(env, "vn_equity_quote_batch")
    for row in env["data"]["quotes"]:
        assert set(row.keys()) == {"symbol", "price"}
