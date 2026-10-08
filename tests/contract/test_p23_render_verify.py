"""Contract: P23 fixes from Render full-matrix verify (sub-batch, fallbacks, shapes)."""

from __future__ import annotations

from typing import Any

from opentrading_mcp.server import create_server, register_all


def _tool_fn(name: str):
    server = create_server()
    register_all(server)
    tool = server._tool_manager.get_tool(name)
    assert tool is not None, f"tool {name} not registered"
    return tool.fn


def _check_envelope(env: dict[str, Any], tool: str) -> None:
    for key in ("data", "provenance", "warnings", "availability"):
        assert key in env, f"{tool}: envelope missing {key!r}"


def test_equity_quote_batch_subbatches_partial(monkeypatch):
    """Render verify: 30-symbol single batch hangs — sub-batch 10s, partial + missing."""
    import opentrading_mcp.providers.vnstock as vn_p

    calls: list[list[str]] = []

    class FakeMarket:
        def __init__(self):
            self._syms: list[str] = []

        def equity(self, syms: list[str]):
            calls.append(list(syms))
            self._syms = syms
            return self

        def quote(self):
            import pandas as pd

            if len(self._syms) > 10:
                raise AssertionError(f"chunk too big: {len(self._syms)}")
            if "HANG" in self._syms:
                import time

                time.sleep(60)
            if "BAD" in self._syms:
                raise RuntimeError("boom")
            return pd.DataFrame([{"symbol": s, "close": 10.0} for s in self._syms])

    import sys
    import types

    fake_vnstock = types.ModuleType("vnstock")
    fake_vnstock.Market = FakeMarket
    monkeypatch.setitem(sys.modules, "vnstock", fake_vnstock)
    rows = vn_p.equity_quote_batch([f"S{i}" for i in range(25)])
    quotes, missing = vn_p.split_batch(rows)
    assert len(calls) == 3, calls  # 10 + 10 + 5
    assert len(quotes) == 25 and not missing

    # one bad chunk → partial, not hang (chunk-level granularity)
    rows = vn_p.equity_quote_batch(["OK1"] * 10 + ["BAD"] + ["OK2"] * 10)
    quotes, missing = vn_p.split_batch(rows)
    assert "BAD" in missing, missing
    assert len(quotes) == 11, len(quotes)


def test_quant_backtest_has_equity_curve(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    monkeypatch.setattr(
        vn_p, "quote_history",
        lambda *a, **k: [{"c": 100.0 + i} for i in range(50)],
    )
    import asyncio

    fn = _tool_fn("quant_backtest")
    env = asyncio.new_event_loop().run_until_complete(fn(symbol="VCB"))
    _check_envelope(env, "quant_backtest")
    curve = env["data"]["equity_curve"]
    assert isinstance(curve, list) and len(curve) > 0
    assert curve[0] == 0.0  # normalized to first close


def test_geo_intel_empty_filter_falls_back(monkeypatch):
    """Filter-all → unfiltered top-5 with warning (not count:0)."""
    from opentrading_mcp.providers import intel as intel_p
    from opentrading_mcp.tools import intel as tools_intel

    def fake_gdelt(query: str = "x", max_records: int = 20):
        return {"query": query, "articles": [
            {"title": "football final", "url": "http://x.com/1"},
            {"title": "tennis results", "url": "http://x.com/2"},
        ]}

    async def fake_call(*a: Any, **k: Any) -> Any:
        return fake_gdelt()

    monkeypatch.setattr(intel_p, "gdelt_events", fake_gdelt)
    monkeypatch.setattr(tools_intel, "_call", fake_call)
    import asyncio

    fn = _tool_fn("geo_intel")
    env = asyncio.new_event_loop().run_until_complete(fn(topic="sports"))
    _check_envelope(env, "geo_intel")
    assert env["data"]["count"] == 2
    assert any("unfiltered" in w for w in (env["warnings"] or []))


def test_yf_yield_curve_fred_fallback(monkeypatch):
    from opentrading_mcp.providers import intel as intel_p
    from opentrading_mcp.providers import yfinance as yf_p
    from opentrading_mcp.providers.errors import ProviderUnavailable

    def boom(*a: Any, **k: Any) -> Any:
        raise ProviderUnavailable("yfinance yield fetch failed")

    def fake_fred(series_id: str, limit: int = 60) -> Any:
        v = "4.29" if "DGS10" in str(series_id) else "3.91"
        return {"series": series_id, "points": [{"t": "2026-10-01", "v": v}]}

    monkeypatch.setattr(yf_p, "yield_curve", boom)
    monkeypatch.setattr(intel_p, "fred_series", fake_fred)
    import asyncio

    fn = _tool_fn("yf_yield_curve")
    env = asyncio.new_event_loop().run_until_complete(fn())
    _check_envelope(env, "yf_yield_curve")
    assert env["data"]["us10y"] == 0.0429
    assert env["provenance"]["source"] == "fred"


def test_crypto_spot_vision_fallback(monkeypatch):
    from opentrading_mcp.providers import binance as bn_p
    from opentrading_mcp.providers.errors import ProviderUnavailable

    calls: list[str] = []

    def fake_get(url: str, params: Any) -> Any:
        calls.append(url)
        if "api.binance.com" in url:
            raise ProviderUnavailable("binance GET failed: 418")
        return [{"symbol": "BTCUSDT", "lastPrice": "85000", "priceChangePercent": "1.0",
                 "highPrice": "86000", "lowPrice": "84000", "volume": "100", "quoteVolume": "1"}]

    monkeypatch.setattr(bn_p, "_get_json", fake_get)
    rows = bn_p.spot_board(["BTCUSDT"])
    assert rows[0]["last"] == 85000.0
    assert any("api.binance.com" in u for u in calls) and any("vision" in u for u in calls)


def test_valuation_run_eps_fallback(monkeypatch):
    """overview lacks EPS → derive from vnstock PE."""
    from opentrading_mcp.tools import compute_financial as comp_fin

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        if tool == "v":
            return {"ClosePrice": 57000}
        if tool == "f":
            return {"pe": 15.0}
        return [{"close_price": 57000.0}]

    monkeypatch.setattr(comp_fin, "_call", fake_call)
    import asyncio

    fn = _tool_fn("valuation_run")
    env = asyncio.new_event_loop().run_until_complete(fn(symbol="VCB", btype=3))
    _check_envelope(env, "valuation_run")
    assert env["data"]["method"] == "pb_bank_broker"
    assert env["data"]["per"] == 15.0
    assert any("vnstock PE" in w for w in (env["warnings"] or []))
