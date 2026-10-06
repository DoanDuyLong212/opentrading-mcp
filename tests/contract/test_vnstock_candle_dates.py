"""vn_quote_history candles carry real ISO dates, not the DataFrame row index."""

from __future__ import annotations

import sys
import types
from datetime import date, datetime

import pandas as pd

from opentrading_mcp.providers import vnstock as vn
from opentrading_mcp.tools.quant_shared import _dated_closes


def test_candle_day_formats():
    assert vn._candle_day(pd.Timestamp("2026-10-06")) == "2026-10-06"
    assert vn._candle_day(datetime(2026, 10, 6, 9, 15)) == "2026-10-06"
    assert vn._candle_day(date(2026, 10, 6)) == "2026-10-06"
    assert vn._candle_day("2026-10-06 00:00:00") == "2026-10-06"
    assert vn._candle_day("15") == "15"  # nothing better to say


def test_quote_history_reads_the_time_column(monkeypatch):
    frame = pd.DataFrame(
        {
            "time": pd.to_datetime(["2026-10-02", "2026-10-05", "2026-10-06"]),
            "open": [63.0, 62.5, 61.9],
            "high": [63.5, 63.0, 62.4],
            "low": [62.8, 62.0, 60.1],
            "close": [63.0, 62.7, 60.2],
            "volume": [3_000_000, 3_400_000, 6_714_000],
        }
    )  # RangeIndex 0..2, like vnstock

    class Quote:
        def __init__(self, symbol: str, source: str) -> None:
            pass

        def history(self, **_: object) -> pd.DataFrame:
            return frame

    monkeypatch.setitem(sys.modules, "vnstock", types.SimpleNamespace(Quote=Quote))
    rows = vn.quote_history.__wrapped__("FPT", 3) if hasattr(vn.quote_history, "__wrapped__") else vn.quote_history("FPT", 3)
    assert [r["t"] for r in rows] == ["2026-10-02", "2026-10-05", "2026-10-06"]
    assert rows[-1]["c"] == 60.2
    # Quant tools now align on real dates instead of a business-day walkback.
    dates, _closes, walked = _dated_closes(rows)
    assert walked is False
    assert dates[0] == date(2026, 10, 2)
