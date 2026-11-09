"""Q4 (owner decision 2026-11-09): during the session the gen-6 daily routes have no
bar for today; vnstock 4 had one. Today's bar is built from today's 1m bars and
flagged partial. Numbers: FPT 2026-11-09 09:31 (v4 daily bar o 51.3 h 51.3 l 50.8)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from opentrading_mcp.providers import vnstock as vn_p


class _Frame:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows

    def to_dict(self, orient: str = "records"):
        return [dict(r) for r in self.rows]

    def __len__(self):
        return len(self.rows)

    @property
    def empty(self):
        return not self.rows


DAILY = [
    {"time": "2026-11-05T07:00:00+07:00", "open": 54.5, "high": 54.6, "low": 52.8,
     "close": 52.9, "volume": 8006200},
    {"time": "2026-11-06T07:00:00+07:00", "open": 51.4, "high": 51.8, "low": 50.8,
     "close": 50.8, "volume": 12162200},
]
MINUTES = [
    {"time": "2026-11-09T09:15:00+07:00", "open": 51.3, "high": 51.3, "low": 51.2,
     "close": 51.2, "volume": 121300},
    {"time": "2026-11-09T09:16:00+07:00", "open": 51.2, "high": 51.2, "low": 51.1,
     "close": 51.1, "volume": 38200},
    {"time": "2026-11-09T09:31:00+07:00", "open": 50.9, "high": 50.9, "low": 50.8,
     "close": 50.8, "volume": 5900},
]


@pytest.fixture
def market(monkeypatch):
    seen: list[str] = []

    def frame_for(interval: str):
        return _Frame(MINUTES if interval == "1m" else DAILY)

    def fetchers(symbol, **kw):
        seen.append(kw.get("interval"))
        return [("ssi", lambda: frame_for(kw.get("interval", "1D")))]

    monkeypatch.setattr(vn_p, "_candle_fetchers", fetchers)
    monkeypatch.setattr(vn_p, "_vn_today", lambda: date(2026, 11, 9))
    vn_p._partial_cache.clear()
    yield seen
    vn_p._partial_cache.clear()


def test_partial_bar_aggregates_todays_minutes(market):
    bar = vn_p._today_partial_bar("FPT")
    assert bar is not None
    assert (bar["open"], bar["high"], bar["low"], bar["close"]) == (51.3, 51.3, 50.8, 50.8)
    assert bar["volume"] == 121300 + 38200 + 5900
    assert bar["day"] == "2026-11-09"


def test_quote_history_gets_todays_bar_flagged_partial(market):
    rows = vn_p._with_today_history("FPT", [{"t": "2026-11-06", "c": 50.8}])
    assert rows[-1]["t"] == "2026-11-09" and rows[-1]["partial"] is True
    assert rows[-1]["c"] == 50.8 and rows[-1]["o"] == 51.3


def test_ohlcv_rows_get_todays_bar(market):
    rows = vn_p._with_today_bars("VNINDEX", list(DAILY))
    assert rows[-1]["time"] == "2026-11-09T07:00:00+07:00" and rows[-1]["partial"] is True


def test_no_extra_bar_once_today_is_published(market):
    published = [*DAILY, {"time": "2026-11-09T07:00:00+07:00", "close": 50.9}]
    assert vn_p._with_today_bars("FPT", published) == published
    assert vn_p._with_today_history("FPT", [{"t": "2026-11-09"}]) == [{"t": "2026-11-09"}]
    assert market == []  # no 1m fetch when today's bar already exists


def test_weekend_and_failures_add_nothing(market, monkeypatch):
    monkeypatch.setattr(vn_p, "_vn_today", lambda: date(2026, 11, 8))  # Sunday
    assert vn_p._with_today_bars("FPT", list(DAILY)) == DAILY
    monkeypatch.setattr(vn_p, "_vn_today", lambda: date(2026, 11, 10))

    def broken(symbol, **kw):
        raise RuntimeError("ssi down")

    monkeypatch.setattr(vn_p, "_candle_fetchers", broken)
    assert vn_p._with_today_bars("FPT", list(DAILY)) == DAILY  # never breaks the answer


def test_partial_bar_is_cached_for_a_minute(market):
    vn_p._today_partial_bar("FPT")
    vn_p._today_partial_bar("FPT")
    assert market.count("1m") == 1
