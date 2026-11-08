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

    class FakeEquityGroup:
        def quote(self, *, symbols=None, **kwargs):
            import pandas as pd

            calls.append(list(symbols or []))
            if len(symbols or []) > 10:
                raise AssertionError(f"chunk too big: {len(symbols)}")
            if "HANG" in symbols:
                import time

                time.sleep(50)
            if "BAD" in symbols:
                raise RuntimeError("boom")
            return pd.DataFrame([{"symbol": s, "close": 10.0} for s in symbols])

    class FakeMarket:
        def __init__(self, source=None, **kwargs):
            pass

        @property
        def equity(self):
            return FakeEquityGroup()

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


def test_equity_quote_batch_hang_returns_promptly():
    """502 regression: a hung vnstock thread must not block past chunk timeouts
    (shutdown(wait=False) — zombie threads must not defeat run_blocking's cap)."""
    import sys
    import time
    import types

    import opentrading_mcp.providers.vnstock as vn_p

    class HangMarket:
        def equity(self, syms: list[str]):
            calls.append(list(syms))
            return self

        def quote(self):
            time.sleep(50)

    calls: list[list[str]] = []
    fake_vnstock = types.ModuleType("vnstock")
    fake_vnstock.Market = HangMarket
    import unittest.mock as mock

    with mock.patch.dict(sys.modules, {"vnstock": fake_vnstock}):
        t0 = time.monotonic()
        try:
            vn_p.equity_quote_batch(["A", "B"])
            raised = None
        except Exception as exc:
            raised = exc
        dt = time.monotonic() - t0
    assert raised is not None and "failed for 2 symbols" in str(raised)
    assert dt < 50.0, f"hung chunk blocked {dt:.1f}s (must return ~45s)"


def test_quant_backtest_has_equity_curve(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    monkeypatch.setattr(
        vn_p,
        "quote_history",
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
        return {
            "query": query,
            "articles": [
                {"title": "football final", "url": "http://x.com/1"},
                {"title": "tennis results", "url": "http://x.com/2"},
            ],
        }

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


def test_crypto_spot_coingecko_last_resort(monkeypatch):
    """Both Binance endpoints 418 → CoinGecko USD fallback (no high/low)."""
    from opentrading_mcp.providers import binance as bn_p
    from opentrading_mcp.providers.errors import ProviderUnavailable

    def fake_get(url: str, params: Any) -> Any:
        if "coingecko" in url:
            return {"bitcoin": {"usd": 82000.0, "usd_24h_change": -1.0, "usd_24h_vol": 100.0}}
        raise ProviderUnavailable("binance GET failed: 418")

    monkeypatch.setattr(bn_p, "_get_json", fake_get)
    rows = bn_p.spot_board(["BTCUSDT"])
    assert rows[0]["last"] == 82000.0
    assert rows[0]["high"] is None  # coingecko has no high/low


def test_crypto_spot_vision_fallback(monkeypatch):
    from opentrading_mcp.providers import binance as bn_p
    from opentrading_mcp.providers.errors import ProviderUnavailable

    calls: list[str] = []

    def fake_get(url: str, params: Any) -> Any:
        calls.append(url)
        if "api.binance.com" in url:
            raise ProviderUnavailable("binance GET failed: 418")
        return [
            {
                "symbol": "BTCUSDT",
                "lastPrice": "85000",
                "priceChangePercent": "1.0",
                "highPrice": "86000",
                "lowPrice": "84000",
                "volume": "100",
                "quoteVolume": "1",
            }
        ]

    monkeypatch.setattr(bn_p, "_get_json", fake_get)
    rows = bn_p.spot_board(["BTCUSDT"])
    assert rows[0]["last"] == 85000.0
    assert any("api.binance.com" in u for u in calls) and any("vision" in u for u in calls)


def test_valuation_run_eps_fallback(monkeypatch):
    """overview lacks EPS → vnstock trailing EPS/BVPS (not price / period-end PE)."""
    from opentrading_mcp.tools import compute_financial as comp_fin

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        if tool == "v":
            return {"ClosePrice": 57000}
        if tool == "f":
            return {"pe": 99.0, "eps": 3800.0, "bvps": 19000.0, "period_label": "2025"}
        return [{"close_price": 57000.0}]

    monkeypatch.setattr(comp_fin, "_call", fake_call)
    import asyncio

    fn = _tool_fn("valuation_run")
    env = asyncio.new_event_loop().run_until_complete(fn(symbol="VCB", btype=3))
    _check_envelope(env, "valuation_run")
    assert env["data"]["method"] == "pb_bank_broker"
    assert env["data"]["per"] == 15.0
    assert env["data"]["pb"] == 3.0
    assert "2025" in env["data"]["eps_source"]


def test_financial_detail_lctt_vnstock_fallback(monkeypatch):
    """Vietstock LCTT norms empty upstream → vnstock cashflow fallback (not unavailable)."""
    from opentrading_mcp.providers import vietstock as vs_p
    from opentrading_mcp.providers import vnstock as vn_p
    from opentrading_mcp.providers.errors import ProviderBadData
    from opentrading_mcp.tools import corp as corp_mod

    def boom_detail(symbol: str, statement: str = "KQKD", periods_n: int = 8) -> dict:
        raise ProviderBadData(f"vietstock no norms for {symbol} {statement}")

    def fake_cf(symbol: str, period: str = "quarter") -> dict:
        return {
            "symbol": symbol,
            "period": period,
            "unit": "VNDbn",
            "periods": ["Q1/2026", "Q2/2026"],
            "rows": [{"name": "Test flow", "values": [1.0, 2.0]}],
        }

    monkeypatch.setattr(vs_p, "financial_detail", boom_detail)
    monkeypatch.setattr(vn_p, "cashflow", fake_cf)
    monkeypatch.setattr(corp_mod, "vs_p", vs_p)
    import asyncio

    server = create_server()
    register_all(server)
    fn = server._tool_manager.get_tool("financial_detail").fn
    env = asyncio.new_event_loop().run_until_complete(fn(symbol="FPT", statement="LCTT"))
    assert env["availability"] == "available", env
    assert env["provenance"]["source"] == "vnstock"
    assert any("LCTT empty upstream" in w for w in env["warnings"])
    assert env["data"]["rows"][0]["name"] == "Test flow"


def test_cashflow_parser_skips_metadata_columns(monkeypatch):
    """Gen-6 wide cashflow frames carry item_en/item_id columns — only period cols become values."""
    import sys
    import types

    import pandas as pd

    import opentrading_mcp.providers.vnstock as vn_p

    class FakeEquity:
        def cash_flow(self, period: str = "quarter", format: str = "wide", **kwargs: Any) -> Any:
            return pd.DataFrame(
                [
                    {
                        "item": "Test flow",
                        "item_en": "x",
                        "item_id": 1,
                        "2026-Q1": 1_000_000_000.0,
                        "2026-Q2": 2_000_000_000.0,
                    },
                ]
            )

    class FakeFundamental:
        def __init__(self, source=None, **kwargs):
            assert source == "fhsc"

        def equity(self, symbol: str) -> FakeEquity:
            return FakeEquity()

    fake_vnstock = types.ModuleType("vnstock")
    fake_vnstock.Fundamental = FakeFundamental
    monkeypatch.setitem(sys.modules, "vnstock", fake_vnstock)
    out = vn_p.cashflow("FPT")
    assert out["periods"] == ["2026-Q1", "2026-Q2"], out["periods"]
    assert out["rows"] == [{"name": "Test flow", "values": [1.0, 2.0]}]
    assert out["rows"][0]["values"] == [1.0, 2.0]  # raw VND → VNDbn


def test_vnstock_api_key_helpers(monkeypatch):
    """Gen 6: per-source keys decide "keyed"; VNSTOCK_API_KEY unlocks the VAS set.
    Never raises, no runtime registration call."""
    import opentrading_mcp.providers.vnstock as vn_p

    for var in ("VNSTOCK_API_KEY", "FHSC_API_KEY", "SSI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert vn_p.ensure_api_key() == "anonymous"
    assert vn_p.quota_info()["tier"] == "anonymous"

    monkeypatch.setenv("VNSTOCK_API_KEY", "vnstock_testkey123")
    assert vn_p.ensure_api_key() == "keyed"
    q = vn_p.quota_info()
    assert isinstance(q, dict) and "tier" in q

    monkeypatch.delenv("VNSTOCK_API_KEY", raising=False)
    monkeypatch.setenv("FHSC_API_KEY", "fhsc_testkey")
    assert vn_p.ensure_api_key() == "keyed"
    assert vn_p.quota_info()["sources"]["fhsc"] is True


def test_market_movers_vn30_default_no_ref_call(monkeypatch):
    """Render verify: default universe is static VN30 (no HOSE ref call that hangs)."""
    from opentrading_mcp.providers import vnstock as vn_p

    seen: list[list[str]] = []

    def fake_batch(symbols: list[str]) -> list[dict]:
        seen.append(list(symbols))
        return [{"symbol": s, "pct_change": 1.0, "volume": 100} for s in symbols]

    def boom_ref(*a: Any, **k: Any) -> Any:
        raise AssertionError("reference_equity must not be called for default vn30")

    monkeypatch.setattr(vn_p, "equity_quote_batch", fake_batch)
    monkeypatch.setattr(vn_p, "reference_equity", boom_ref)
    import asyncio

    server = create_server()
    register_all(server)
    fn = server._tool_manager.get_tool("market_movers").fn
    env = asyncio.new_event_loop().run_until_complete(fn(top_n=2))
    assert env["availability"] == "available", env
    assert env["data"]["universe"] == 30, env["data"]
    assert len(env["data"]["gainers"]) == 2
    assert len(seen) == 1 and len(seen[0]) == 30


def test_market_movers_sorts_by_percent_change():
    """Render verify: quote dicts use percent_change/volume_accumulated keys."""
    import asyncio

    server = create_server()
    register_all(server)
    fn = server._tool_manager.get_tool("market_movers").fn

    import unittest.mock as mock

    import opentrading_mcp.providers.vnstock as vn_p

    def fake_batch(symbols):
        return [
            {"symbol": s, "percent_change": float(i), "volume_accumulated": 100 - i}
            for i, s in enumerate(symbols[:5])
        ]

    async def go():
        with mock.patch.object(vn_p, "equity_quote_batch", fake_batch):
            return await fn(top_n=2)

    env = asyncio.new_event_loop().run_until_complete(go())
    assert env["availability"] == "available", env
    gainers = [g["symbol"] for g in env["data"]["gainers"]]
    # fake assigns percent_change=idx (ACB=0…); desc sort → highest idx first
    assert gainers[0] == "CTG" and gainers[1] == "BVH", gainers
    assert env["data"]["universe"] == 5  # = quotes count (fake returns 5 rows)
