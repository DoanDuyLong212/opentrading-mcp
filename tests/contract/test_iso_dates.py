"""Envelopes carry ISO dates, never ASP.NET's /Date(ms)/ (models cannot read it).

On 2026-10-11 stock_overview returned "TradingDate": "/Date(1791532464487)/"
(Friday 09/10 14:54 Vietnam time); the model took provenance.as_of, the
Sunday fetch time, as the trading date.
"""

from __future__ import annotations

from opentrading_mcp.schemas import make_envelope, normalize_dates


def test_trading_time_keeps_its_time_of_day_in_vietnam_time() -> None:
    env = make_envelope({"trading": {"TradingDate": "/Date(1791532464487)/"}}, source="vietstock")
    assert env["data"]["trading"]["TradingDate"] == "2026-10-09T14:54:24+07:00"


def test_midnight_dates_stay_plain_dates_nested_in_rows() -> None:
    data = {
        "rows": [{"ReportDate": "/Date(1784739600000)/", "Value": 1.5}],
        "tuple": ("/Date(1784739600000+0700)/",),
    }
    out = normalize_dates(data)
    assert out["rows"][0] == {"ReportDate": "2026-07-23", "Value": 1.5}
    assert out["tuple"] == ("2026-07-23",)


def test_other_strings_are_untouched() -> None:
    data = {
        "note": "xem /Date(1784739600000)/ trong văn bản",
        "bad": "/Date(abc)/",
        "n": 3,
        "none": None,
    }
    assert normalize_dates(data) == data
