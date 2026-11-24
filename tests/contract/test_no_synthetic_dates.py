"""#137: a missing bar date is disclosed, never invented.

The old contract built a business-day walkback ending *today* whenever any bar
lacked a date, so one day-only ``t`` silently relabelled a whole series and
month filters, seasonality buckets and correlations ran on made-up dates.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd
import pytest

from opentrading_mcp.providers.errors import ProviderBadData
from opentrading_mcp.tools import quant_shared


def _candles(prices: list[float], start: str = "2026-01-05") -> list[dict[str, Any]]:
    base = date.fromisoformat(start)
    return [
        {
            "t": (base + timedelta(days=i)).isoformat(),
            "o": c - 0.1,
            "h": c + 0.3,
            "l": c - 0.3,
            "c": c,
            "v": 1000.0,
        }
        for i, c in enumerate(prices)
    ]


def _tool_fn(name: str):
    from opentrading_mcp.server import create_server, register_preset

    server = create_server("quant")
    register_preset(server, "quant")
    tool = server._tool_manager.get_tool(name)
    assert tool is not None
    return tool.fn


# ---- unit: _dated_closes ---------------------------------------------------


def test_one_missing_date_keeps_the_real_ones():
    rows = _candles([10.0, 11.0, 12.0, 13.0])
    rows[2]["t"] = "15"  # vnstock day-only label: carries no date
    dates, closes, missing = quant_shared._dated_closes(rows)
    assert len(dates) == len(closes) == 4
    assert dates[0] == date(2026, 1, 5)
    assert dates[1] == date(2026, 1, 6)
    assert dates[2] is None  # disclosed gap, not a guessed business day
    assert dates[3] == date(2026, 1, 8)
    assert missing is True


def test_undated_series_is_never_stamped_with_today():
    rows = [{"t": str(i), "c": 10.0 + i} for i in range(5)]
    dates, closes, missing = quant_shared._dated_closes(rows)
    assert missing is True
    assert all(d is None for d in dates)
    assert len(closes) == 5


def test_fully_dated_series_is_unchanged():
    rows = _candles([10.0, 11.0])
    dates, _closes, missing = quant_shared._dated_closes(rows)
    assert missing is False
    assert dates == [date(2026, 1, 5), date(2026, 1, 6)]


# ---- unit: yfinance condition series --------------------------------------


def test_yf_series_without_usable_dates_is_refused(monkeypatch):
    import sys
    import types

    class Ticker:
        def __init__(self, symbol: str) -> None:
            pass

        def history(self, **_kwargs: object) -> pd.DataFrame:
            # An integer index carries no observation date at all.
            return pd.DataFrame({"Close": [10.0 + i for i in range(40)]})

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=Ticker))
    with pytest.raises(ProviderBadData):
        quant_shared._yf_closes("GC=F")


def test_yf_series_keeps_its_real_dates(monkeypatch):
    import sys
    import types

    class Ticker:
        def __init__(self, symbol: str) -> None:
            pass

        def history(self, **_kwargs: object) -> pd.DataFrame:
            return pd.DataFrame(
                {"Close": [10.0 + i for i in range(40)]},
                index=pd.to_datetime([date(2026, 1, 5) + timedelta(days=i) for i in range(40)]),
            )

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=Ticker))
    dates, closes = quant_shared._yf_closes("GC=F")
    assert len(dates) == len(closes) == 40
    assert dates[0] == date(2026, 1, 5)


# ---- unit: calendar filters cannot silently become no-ops -----------------


def test_month_filter_never_authorizes_an_undated_bar():
    prices = [10.0 + 0.1 * i for i in range(40)]
    out = quant_shared._run_strategy(
        prices,
        "buy_hold",
        5,
        20,
        10.0,
        dates=[None] * len(prices),
        months=[1],
    )
    assert out["trades"] == 0
    assert out["undated_bars_blocked"] == len(prices)
    assert "date" in out["note"].lower()


def test_month_filter_still_trades_when_dates_are_real():
    prices = [10.0 + 0.1 * i for i in range(40)]
    dates = [date(2026, 1, 5) + timedelta(days=i) for i in range(40)]
    out = quant_shared._run_strategy(prices, "buy_hold", 5, 20, 10.0, dates=dates, months=[1])
    assert out["trades"] == 1
    assert "undated_bars_blocked" not in out


# ---- unit: alignment ------------------------------------------------------


def test_align_returns_drops_undated_bars_and_flags_it():
    a = _candles([10.0, 11.0, 12.0, 13.0])
    b = _candles([20.0, 21.0, 22.0, 23.0])
    b[1]["t"] = "15"
    common, aligned, dates_missing = quant_shared._align_returns({"A": a, "B": b})
    assert dates_missing is True
    assert None not in common
    # Jan 6 exists only as an undated bar in B: the join keeps the dated ones.
    assert common == [date(2026, 1, 5), date(2026, 1, 7), date(2026, 1, 8)]
    assert len(aligned["A"]) == len(aligned["B"]) == len(common) - 1


# ---- tools ---------------------------------------------------------------


async def _undated_history(symbol: str, days: int = 365) -> list[dict[str, Any]]:
    return [{"t": str(i), "o": 10.0 + i, "h": 10.5 + i, "l": 9.5 + i, "c": 10.0 + i, "v": 1.0}
            for i in range(60)]


async def test_backtest_discloses_missing_dates_instead_of_inventing(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    def _history(symbol: str, days: int = 365):
        return [{"t": str(i), "o": 10.0 + i, "h": 10.5 + i, "l": 9.5 + i, "c": 10.0 + i, "v": 1.0}
                for i in range(60)]

    monkeypatch.setattr(vn_p, "quote_history", _history)
    env = await _tool_fn("backtest_strategies")(
        symbol="FPT", strategy="buy_hold", months=[1], fast=5, slow=20
    )
    assert env["data"]["trades"] == 0
    assert env["data"]["date_basis"] != "observed"
    assert env["data"]["undated_bars_blocked"] == 60
    assert env["availability"] == "partial"
    assert any("date" in w.lower() for w in env["warnings"])


async def test_backtest_without_dates_still_runs_order_only(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    def _history(symbol: str, days: int = 365):
        return [{"t": str(i), "o": 10.0 + i, "h": 10.5 + i, "l": 9.5 + i, "c": 10.0 + i, "v": 1.0}
                for i in range(60)]

    monkeypatch.setattr(vn_p, "quote_history", _history)
    env = await _tool_fn("backtest_strategies")(symbol="FPT", strategy="buy_hold", fast=5, slow=20)
    # Order-only strategies keep working, but the payload says the dates are missing.
    assert env["data"]["bars"] == 60
    assert env["data"]["stale"] is True
    assert env["data"]["date_basis"] == "missing"


async def test_seasonality_refuses_to_bucket_undated_bars(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    def _history(symbol: str, days: int = 365):
        return [{"t": str(i), "c": 10.0 + i} for i in range(60)]

    monkeypatch.setattr(vn_p, "quote_history", _history)
    env = await _tool_fn("seasonality")(symbol="FPT")
    assert env["availability"] == "unavailable"
    assert env["data"]["months"] == {}
    assert any("date" in w.lower() for w in env["warnings"])


async def test_correlation_reports_undated_bars_instead_of_guessing(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    def _history(symbol: str, days: int = 365):
        return [{"t": str(i), "c": 10.0 + i} for i in range(60)]

    monkeypatch.setattr(vn_p, "quote_history", _history)
    env = await _tool_fn("correlation_matrix")(symbols=["FPT", "VCB"], days=60)
    assert env["availability"] in ("unavailable", "empty")
    assert env["data"].get("matrix") in (None, {})
    assert any("date" in w.lower() for w in env["warnings"])
