"""#136: market dates come from the VN clock, not the container's UTC clock."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from opentrading_mcp import vn_time


def test_vn_today_flips_at_vn_midnight_not_utc_midnight():
    assert vn_time.vn_today(datetime(2026, 11, 16, 16, 59, tzinfo=UTC)) == date(2026, 11, 16)
    assert vn_time.vn_today(datetime(2026, 11, 16, 17, 0, tzinfo=UTC)) == date(2026, 11, 17)


def test_vn_today_crosses_the_new_year_in_vn_time():
    # 31/12 17:30 UTC is already 01/01 00:30 in VN: the year must roll over.
    assert vn_time.vn_today(datetime(2026, 12, 31, 17, 30, tzinfo=UTC)) == date(2027, 1, 1)


def test_naive_input_is_read_as_vn_wall_time():
    assert vn_time.vn_today(datetime(2026, 11, 16, 0, 30)) == date(2026, 11, 16)


def test_utc_aware_now_is_converted_not_truncated():
    utc_moment = datetime(2026, 11, 16, 20, 0, tzinfo=UTC)
    assert vn_time.vn_now(utc_moment).hour == 3
    assert vn_time.vn_now(utc_moment).utcoffset().total_seconds() == 7 * 3600


def test_iso_label_matches_vn_today():
    assert vn_time.vn_today_iso(datetime(2026, 11, 16, 17, 0, tzinfo=UTC)) == "2026-11-17"


def test_market_history_window_uses_the_vn_date(monkeypatch):
    """A candle request at 17:30 UTC (00:30 VN next day) must end on the VN date."""
    from opentrading_mcp.providers import vnstock as vn_p
    from opentrading_mcp.providers.errors import ProviderUnavailable

    seen: dict[str, str] = {}

    def _fetchers(symbol: str, *, start: str, end: str, interval: str):
        seen["start"] = start
        seen["end"] = end
        return []

    monkeypatch.setattr(vn_p, "_candle_fetchers", _fetchers)
    monkeypatch.setattr(vn_p, "vn_today", lambda moment=None: date(2026, 11, 17))
    with pytest.raises(ProviderUnavailable):
        vn_p.quote_history("FPT", days=10)
    assert seen["end"] == "2026-11-17"


def test_macro_window_end_date_is_a_vn_date(monkeypatch):
    from opentrading_mcp.providers import store, vietstock as vs_p

    captured: dict[str, dict] = {}

    def _browser_post(path: str, payload: dict):
        captured["payload"] = payload
        return {"Data": []}

    monkeypatch.setattr(vs_p, "_browser_post", _browser_post)
    monkeypatch.setattr(vs_p, "_parse_pipe_rows", lambda body: [])
    monkeypatch.setattr(vs_p, "vn_today", lambda moment=None: date(2026, 11, 17))
    monkeypatch.setattr(store, "cache_get", lambda key: None)
    monkeypatch.setattr(store, "cache_set", lambda key, value, ttl=None: None)
    vs_p.macro_report_data(1, 2, from_date="2026-01-01")
    assert captured["payload"]["toDate"] == "2026-11-17"
