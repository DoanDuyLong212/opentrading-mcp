"""vnstock ratio frames in long format, candle counts, no-session bars.

Fixture: live vn_fundamentals output for FPT on 2026-10-23. vnstock now returns
ratios as rows (item, item_id, one column per period); the old parser looked
for a `pe` column or index label, found none, and every screener/valuation call
got pe/roe = None.
"""

from __future__ import annotations

import json
import sys
import types
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from opentrading_mcp.providers import vnstock as vn
from opentrading_mcp.providers.errors import ProviderBadData

RATIOS = json.loads(
    (Path(__file__).parent / "fixtures" / "vnstock_ratio_fpt_20261023.json").read_text(
        encoding="utf-8"
    )
)


def _fake_fundamental(monkeypatch, frame: pd.DataFrame) -> None:
    class _Equity:
        def ratio(self, period: str = "year") -> pd.DataFrame:
            return frame

    class Fundamental:
        def equity(self, symbol: str) -> _Equity:
            return _Equity()

    monkeypatch.setitem(sys.modules, "vnstock", types.SimpleNamespace(Fundamental=Fundamental))


def test_long_ratio_picks_the_newest_year():
    values, label = vn._long_ratio_values(pd.DataFrame(RATIOS["year"]))
    assert label == "2025"
    assert values["p_e"] == 15.91
    assert values["trailing_eps"] == 6021.21


def test_long_ratio_quarter_mislabelled_frame_is_refused():
    # columns: 2026-Q2, 2025-Q4, 2026-Q1, 2025-Q4_1 (as returned). The 15.53 this
    # used to read as the 2026-Q2 P/E belongs to another quarter.
    with pytest.raises(ProviderBadData):
        vn._check_ratio_periods(pd.DataFrame(RATIOS["quarter"]))


def test_long_ratio_returns_none_for_other_layouts():
    assert vn._long_ratio_values(pd.DataFrame({"P/E": [12.5], "ROE": [0.18]})) is None


def test_equity_fundamentals_reads_long_format(monkeypatch):
    _fake_fundamental(monkeypatch, pd.DataFrame(RATIOS["year"]))
    out = vn.equity_fundamentals("fpt")
    assert {key: out[key] for key in (
        "symbol", "pe", "roe", "market_cap", "eps", "bvps", "period_label"
    )} == {
        "symbol": "FPT",
        "pe": 15.91,
        "roe": pytest.approx(0.283),
        "market_cap": None,
        "eps": 6021.21,
        "bvps": 25679.55,
        "period_label": "2025",
    }
    assert out["frequency"] == "annual"
    assert out["eps_basis"] == "trailing_four_quarters"
    assert out["discarded_period_labels"] == []
    assert out["market_cap_status"] == "missing_from_ratio_table"


def test_equity_fundamentals_small_roe_is_still_percent(monkeypatch):
    rows = [dict(r) for r in RATIOS["year"]]
    for r in rows:
        if r["item_id"] == "roe":
            r["2025"] = 0.9  # 0.9% — the old >1 heuristic would read this as 90%
    _fake_fundamental(monkeypatch, pd.DataFrame(rows))
    assert vn.equity_fundamentals("X")["roe"] == pytest.approx(0.009)


def test_equity_fundamentals_keeps_valid_zeros(monkeypatch):
    # A finite 0 from the source is a value, not missing data (a break-even
    # company reports EPS/ROE 0). Only an absent row or a non-finite cell is None.
    rows = [dict(r) for r in RATIOS["year"]]
    for r in rows:
        if r["item_id"] in ("p_e", "roe"):
            r["2025"] = 0
        elif r["item_id"] == "book_value_per_share_bvps":
            r["2025"] = "0"  # string zero still parses to a finite 0
    _fake_fundamental(monkeypatch, pd.DataFrame(rows))
    out = vn.equity_fundamentals("FPT")
    assert out["pe"] == 0
    assert out["roe"] == 0
    assert out["bvps"] == 0
    assert out["eps"] == 6021.21  # untouched fields keep their values


def _fake_quote(monkeypatch, frame: pd.DataFrame, seen: dict[str, Any]) -> None:
    class Quote:
        def __init__(self, symbol: str, source: str) -> None:
            pass

        def history(self, start: str, end: str, interval: str) -> pd.DataFrame:
            seen["start"] = start
            return frame

    monkeypatch.setitem(sys.modules, "vnstock", types.SimpleNamespace(Quote=Quote))


def _daily(n: int) -> pd.DataFrame:
    days = pd.bdate_range(end="2026-10-22", periods=n)
    return pd.DataFrame(
        {"time": days, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}
    )


def test_daily_window_asks_far_enough_back_for_the_candle_count(monkeypatch):
    seen: dict[str, Any] = {}
    _fake_quote(monkeypatch, _daily(400), seen)
    rows = vn.quote_history("FPT", 365)
    assert len(rows) == 365
    # 365 sessions need ~1.45 calendar years plus holidays; the old window was 395 days.
    span = (date.today() - date.fromisoformat(seen["start"])).days
    assert span >= 365 * 1.5


def test_no_session_bar_is_dropped(monkeypatch):
    # Live FPT 1W: the Tet week (2026-02-22) came back with o/h/l/c = NaN, volume 0.
    weeks = pd.date_range(end="2026-10-25", periods=40, freq="W-SUN")
    frame = pd.DataFrame(
        {"time": weeks, "open": 60.0, "high": 61.0, "low": 59.0, "close": 60.5, "volume": 1e6}
    )
    tet = weeks.get_loc(pd.Timestamp("2026-02-22"))
    frame.loc[tet, ["open", "high", "low", "close"]] = float("nan")
    frame.loc[tet, "volume"] = 0.0
    _fake_quote(monkeypatch, frame, {})
    rows = vn.quote_history("FPT", 39, "1W")
    assert len(rows) == 39
    assert "2026-02-22" not in [r["t"] for r in rows]
    assert all(r["c"] == 60.5 for r in rows)


async def test_valuation_run_uses_trailing_eps_not_price_over_pe(monkeypatch):
    from opentrading_mcp.server import create_server, register_preset
    from opentrading_mcp.tools import compute_financial as comp_fin

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        if fn is comp_fin.vs_p.overview_trading:
            return {"data": [{"StockCode": "FPT", "ClosePrice": 57400}]}  # live: no EPS
        if fn is comp_fin.vn_p.equity_quote_batch:
            return [{"symbol": "FPT", "close_price": 57400}]
        if fn is comp_fin.vn_p.equity_fundamentals:
            return {
                "pe": 15.91, "eps": 6021.21, "bvps": 25679.55,
                "period_label": "2025", "frequency": "annual",
                "eps_basis": "trailing_four_quarters",
            }
        raise AssertionError(fn)

    monkeypatch.setattr(comp_fin, "_call", fake_call)
    server = create_server("scan")
    register_preset(server, "scan")
    env = await server._tool_manager.get_tool("valuation_run").fn(symbol="FPT")
    data = env["data"]
    assert data["per"] == round(57400 / 6021.21, 2)  # 9.53, not 57400 / (57400 / 15.91)
    assert data["pb"] == round(57400 / 25679.55, 2)
    assert "2025" in data["eps_source"]
    assert data["eps_period"] == "2025"
    assert data["eps_frequency"] == "annual"
    assert data["eps_basis"] == "trailing_four_quarters"
    assert data["price_as_of"] is None
    assert data["price_unit"] == "unverified"
    assert data["price_adjustment_basis"] == "unverified"
    assert data["per_basis"] == "quote_price_over_reported_eps"
    assert env["availability"] == "available"


async def test_valuation_run_flags_missing_inputs(monkeypatch):
    from opentrading_mcp.server import create_server, register_preset
    from opentrading_mcp.tools import compute_financial as comp_fin

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        if fn is comp_fin.vn_p.equity_quote_batch:
            return [{"symbol": "FPT", "close_price": 57400}]
        if fn is comp_fin.vn_p.equity_fundamentals:
            return {"pe": None, "eps": None, "bvps": None, "period_label": None}
        return {"data": []}

    monkeypatch.setattr(comp_fin, "_call", fake_call)
    server = create_server("scan")
    register_preset(server, "scan")
    env = await server._tool_manager.get_tool("valuation_run").fn(symbol="FPT")
    assert env["availability"] == "partial"
    assert "per" not in env["data"] and "pb" not in env["data"]


async def test_valuation_run_cache_hit_shares_fingerprint(monkeypatch):
    # Lookup and store must share one fingerprint: the second call returns the
    # cached envelope without calling any provider again. The v2 bump once
    # changed only the lookup, so every call recomputed and the cache was dead.
    from opentrading_mcp.providers import store
    from opentrading_mcp.server import create_server, register_preset
    from opentrading_mcp.tools import compute_financial as comp_fin

    calls: list[str] = []

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        calls.append(tool)
        if fn is comp_fin.vs_p.overview_trading:
            return {"data": [{"StockCode": "FPT", "ClosePrice": 57400}]}  # no EPS
        if fn is comp_fin.vn_p.equity_quote_batch:
            return [{"symbol": "FPT", "close_price": 57400}]
        if fn is comp_fin.vn_p.equity_fundamentals:
            return {"pe": 15.91, "eps": 6021.21, "bvps": 25679.55, "period_label": "2025"}
        raise AssertionError(fn)

    monkeypatch.setattr(comp_fin, "_call", fake_call)
    monkeypatch.setattr(store, "_memory", {})
    server = create_server("scan")
    register_preset(server, "scan")
    tool = server._tool_manager.get_tool("valuation_run").fn
    env = await tool(symbol="FPT")
    assert env["data"]["per"] == round(57400 / 6021.21, 2)
    env2 = await tool(symbol="FPT")
    assert env2["provenance"].get("cached") is True
    assert env2["data"] == env["data"]
    assert len(calls) == 3  # 3 provider calls once; the cache serves the rest
