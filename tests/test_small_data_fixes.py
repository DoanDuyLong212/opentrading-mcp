"""Small data-correctness fixes found in the 23/10/2026 review (one test group each)."""

from __future__ import annotations

import json
import sys
import types
from typing import Any

import pandas as pd
import pytest

from opentrading_mcp.server import create_server, register_all, register_preset


def _tool(name: str, preset: str = "scan"):
    server = create_server(preset)
    register_preset(server, preset)
    tool = server._tool_manager.get_tool(name)
    assert tool is not None, name
    return tool.fn


# --- financial_lctt: ReportTermID 9 is "6T đầu năm", not a full year ----------------


def test_lctt_labels_half_year_terms_as_6t(monkeypatch):
    from opentrading_mcp.providers import vietstock as vs_p

    norms = [
        {"Name": "LƯU CHUYỂN TIỀN TỆ (PHƯƠNG PHÁP GIÁN TIẾP)", "ReportNormID": -1},
        {"Name": "Lưu chuyển tiền thuần từ hoạt động kinh doanh", "ReportNormID": 2234},
    ]
    rows = [  # live FPT: PBT 6T/2026 5714.2 = Q1 2803.8 + Q2 2910
        {"ReportNormId": 2234, "YearPeriod": 2026, "ReportTermID": 2, "Value": -2847.8e9},
        {"ReportNormId": 2234, "YearPeriod": 2026, "ReportTermID": 9, "Value": -1145.7e9},
    ]
    monkeypatch.setattr(vs_p, "financial_norms", lambda btype=1: norms)
    monkeypatch.setattr(vs_p, "_post_json", lambda *a, **k: {"data": rows})
    out = vs_p.financial_lctt("FPT", 1)
    assert out["periods"] == ["Q1/2026", "6T/2026"]
    assert out["rows"][0]["values"] == [-2847.8, -1145.7]


# --- yf_yield_curve: FRED points are newest first ----------------------------------


async def test_yield_curve_fred_fallback_takes_the_newest_point(monkeypatch):
    from opentrading_mcp.providers import intel as intel_p
    from opentrading_mcp.providers import yfinance as yf_p
    from opentrading_mcp.providers.errors import ProviderUnavailable

    def blocked() -> Any:
        raise ProviderUnavailable("yfinance blocked")

    def fred(series_id: str, limit: int = 60) -> dict[str, Any]:
        newest, oldest = ("4.25", "4.10") if series_id == "DGS10" else ("3.90", "3.70")
        return {"series": series_id, "points": [{"t": "2026-10-22", "v": newest},
                                                {"t": "2026-10-16", "v": oldest}]}

    monkeypatch.setattr(yf_p, "yield_curve", blocked)
    monkeypatch.setattr(intel_p, "fred_series", fred)
    from opentrading_mcp.providers import store

    monkeypatch.setattr(store, "_memory", {})
    env = await _tool("yf_yield_curve", "all")()
    assert env["data"] == {"us10y": 0.0425, "us2y": 0.039, "inverted": False}


# --- scenario_simulate: P/L from the unrounded price, with units ----------------------


async def test_scenario_pnl_is_exact_and_has_units(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    monkeypatch.setattr(vn_p, "quote_history", lambda *a, **k: [{"t": "2026-10-22", "c": 21.25}])
    server = create_server()
    register_all(server)
    env = await server._tool_manager.get_tool("scenario_simulate").run(
        {"scenario": "x", "symbol": "HPG", "shock_pct": -5.0}
    )
    assert env["data"]["shocked_price"] == 20.19
    assert env["data"]["pnl_per_1000_shares"] == -1062.5  # not -1060 from the rounded price
    assert "nghìn đồng" in env["units"]["pnl_per_1000_shares"]


# --- units: index candles are points --------------------------------------------------


def test_index_candles_are_labelled_points():
    from opentrading_mcp.units import POINTS, THOUSAND_DONG, with_units

    index = with_units("vn_quote_history", {"data": {"symbol": "VNINDEX", "candles": []}})
    stock = with_units("vn_quote_history", {"data": {"symbol": "VNM", "candles": []}})
    assert index["units"]["o, h, l, c, last, high, low"] == POINTS
    assert stock["units"]["o, h, l, c, last, high, low"] == THOUSAND_DONG
    mixed = with_units(
        "market_candles_batch",
        {"data": {"series": [{"symbol": "FPT"}, {"symbol": "VN30"}], "missing": []}},
    )
    assert "VN30" in mixed["units"]["o, h, l, c, last, high, low"]
    only_index = with_units(
        "market_candles_batch", {"data": {"series": [{"symbol": "VNINDEX"}], "missing": []}}
    )
    assert only_index["units"]["o, h, l, c, last, high, low"] == POINTS


# --- regime_assets: one calendar year back ----------------------------------------------


def test_regime_change_is_one_calendar_year_for_a_7_day_market(monkeypatch):
    from opentrading_mcp.providers import yfinance as yf_p

    days = pd.date_range(end="2026-10-22", periods=500, freq="D")  # trades every day
    close = pd.Series(range(100, 600), index=days, dtype=float)
    frame = pd.concat({t: pd.DataFrame({"Close": close}) for t in yf_p.REGIME_7}, axis=1)
    fake_yf = types.SimpleNamespace(download=lambda *a, **k: frame)
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)
    out = yf_p.regime_assets()
    year_ago = float(close[close.index <= days[-1] - pd.Timedelta(days=365)].iloc[-1])
    assert out["BTC-USD"]["chg_1y_pct"] == round((599 - year_ago) / year_ago * 100, 2)


# --- signals_scan: truncated when the pool is larger than max_symbols ------------------


async def test_signals_scan_reports_truncation(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    monkeypatch.setattr(
        vn_p, "reference_equity", lambda *a, **k: [{"symbol": f"S{i}"} for i in range(10)]
    )
    monkeypatch.setattr(vn_p, "quote_history", lambda *a, **k: [{"c": 1.0}] * 25)
    env = await _tool("signals_scan")(exchange="HOSE", max_symbols=3)
    assert env["data"]["requested"] == 3
    assert env["data"]["truncated"] is True and env["data"]["available"] == 10


# --- watchlist_add: added counts new symbols -------------------------------------------


@pytest.fixture()
def file_store(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr("opentrading_mcp.tools.watchlist._data_dir", tmp_path)
    from opentrading_mcp.providers import store

    monkeypatch.setattr(store, "_memory", {})
    return tmp_path


async def test_watchlist_add_counts_only_new_symbols(file_store):
    wl = (await _tool("watchlist_create")("core"))["data"]
    await _tool("watchlist_add")(wl["id"], ["VCB"])
    env = await _tool("watchlist_add")(wl["id"], ["VCB", "HPG"])
    assert env["data"]["added"] == 1
    assert env["data"]["symbols"] == ["VCB", "HPG"]


# --- quant_factors: 20 sessions back, drawdown in time order ---------------------------


async def test_quant_factors_momentum_and_drawdown(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    closes = [100.0] * 40 + [float(p) for p in range(80, 100)]  # last 20: steady rise
    candles = [{"t": f"d{i}", "c": c} for i, c in enumerate(closes)]
    monkeypatch.setattr(vn_p, "quote_history", lambda *a, **k: candles)
    data = (await _tool("quant_factors")(symbol="FPT", lookback=60))["data"]
    assert data["momentum_20d_pct"] == round((99 - 100) / 100 * 100, 2)  # vs closes[-21]
    assert data["max_dd_20d_pct"] == 0.0  # the low came first: no drawdown
    assert data["max_dd_full_pct"] == 20.0


# --- vn_equity_quote_batch summary: the sentinel row is not a quote --------------------


async def test_quote_batch_summary_excludes_missing_sentinel(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    monkeypatch.setattr(
        vn_p, "equity_quote_batch",
        lambda symbols: [{"symbol": "FPT", "close_price": 57400}, {"_missing": ["XYZ"]}],
    )
    data = (await _tool("vn_equity_quote_batch", "all")(symbols=["FPT", "XYZ"], summary=True))
    assert data["data"] == {"count": 1, "symbols": ["FPT"], "missing": ["XYZ"]}


# --- Binance -> CoinGecko fallback: USD volume is quote volume --------------------------


def test_coingecko_volume_is_quote_volume(monkeypatch):
    from opentrading_mcp.providers import binance as bn

    def fake_get(url: str, params: dict[str, Any]) -> Any:
        if "coingecko" in url:
            return {"bitcoin": {"usd": 100000.0, "usd_24h_change": 1.5, "usd_24h_vol": 3.2e10}}
        raise RuntimeError("418")

    monkeypatch.setattr(bn, "_get_json", fake_get)
    row = bn.spot_board(["BTCUSDT"])
    assert row[0]["volume"] is None
    assert row[0]["quote_volume"] == 3.2e10


# --- GDELT: seendate as ISO, so day filters and by_day work ----------------------------


def test_gdelt_seendate_becomes_iso():
    from opentrading_mcp.providers.intel import _gdelt_date

    assert _gdelt_date("20261023T101500Z") == "2026-10-23T10:15:00Z"
    assert _gdelt_date("2026-10-23") == "2026-10-23"
    assert _gdelt_date(None) is None


def test_geo_aggregate_groups_by_calendar_day():
    from opentrading_mcp.providers import geo as geo_p
    from opentrading_mcp.providers.intel import _gdelt_date

    articles = [{"date": _gdelt_date(d), "url": "https://x.com/a"}
                for d in ("20261023T011500Z", "20261023T221500Z", "20261022T120000Z")]
    assert geo_p.aggregate(articles)["by_day"] == {"2026-10-23": 2, "2026-10-22": 1}
    json.dumps(articles)  # still plain strings
