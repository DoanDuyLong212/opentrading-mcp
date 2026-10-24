"""Cycle/asset table maths and the backtest condition gate (pure functions only).

These tables are rebuilt by cycle_stats_finalize / vn_asset_refresh /
g_asset_refresh against Postgres; the tests exercise the extracted helpers.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from opentrading_mcp.tools.cycle_stats import _complete_months, _major_troughs
from opentrading_mcp.tools.quant_shared import _condition_gate


def _series(values: list[float]) -> pd.Series:
    days = pd.date_range("2021-01-01", periods=len(values), freq="D")
    return pd.Series(values, index=days, dtype=float)


def test_trough_after_a_shallow_rebound_is_the_new_one():
    # 100 -> 84 (-16%) -> 100.5 (new peak, only +19.6%: no event)
    #     -> 85 (-15.4% from 100.5) -> 110 (+29%: event at the 85 low)
    s = _series([100, 92, 84, 90, 100.5, 95, 85, 95, 110])
    assert _major_troughs(s) == [(s.index[6], s.index[8])]  # confirmed at the new peak


def test_a_single_deep_drawdown_is_one_trough():
    s = _series([100, 90, 80, 85, 99, 121])
    assert _major_troughs(s) == [(s.index[2], s.index[5])]


def test_no_event_until_a_new_peak():
    # 100 -> 80 -> 97: +21.25% off the trough but never a new peak — the current
    # rule keeps the drawdown open, so no event and no confirmation date.
    s = _series([100, 90, 80, 85, 97])
    assert _major_troughs(s) == []


def test_confirmation_date_is_the_first_new_peak_above_the_rebound_bar():
    # 100 -> 80 -> 96 (+20.0% off the trough, still below the old peak)
    #     -> 101 (new peak: the event is first knowable here).
    s = _series([100, 90, 80, 90, 96, 88, 101])
    trough, confirmed = _major_troughs(s)[0]
    assert s[trough] == 80
    assert confirmed == s.index[6]
    assert confirmed > trough


def test_running_month_is_dropped_but_past_months_stay():
    monthly = pd.DataFrame(
        {"VNINDEX": [0.01, -0.02, 0.03]},
        index=pd.period_range("2026-08", periods=3, freq="M"),
    )
    assert list(_complete_months(monthly, dt.date(2026, 10, 23)).index.astype(str)) == [
        "2026-08", "2026-09"]
    assert len(_complete_months(monthly, dt.date(2026, 11, 2))) == 3
    by_end = monthly.copy()
    by_end.index = by_end.index.to_timestamp(how="end").normalize()  # resample("ME") form
    assert len(_complete_months(by_end, dt.date(2026, 10, 23))) == 2


def test_condition_history_uses_the_nearest_prior_close():
    stock = [dt.date(2026, 6, 29) + dt.timedelta(days=i) for i in range(10)]
    stock = [d for d in stock if d.weekday() < 5]  # VN sessions
    us_holiday = dt.date(2026, 7, 3)
    cond_dates = [d for d in stock if d != us_holiday]
    cond_closes = [float(i) for i in range(len(cond_dates))]  # rising
    gate = _condition_gate(stock, cond_dates, cond_closes, "rising", 3)
    # every bar from the 3rd on has a full 3-bar window, the holiday included
    assert gate[2:] == [True] * (len(stock) - 2)
