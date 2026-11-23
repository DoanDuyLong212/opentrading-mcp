"""Unit tests for the DNSE WS market-window gate (offline, no network).

Ngoài giờ giao dịch, vòng lặp WS phải ngủ tới phiên kế tiếp (hoặc ngắt kết nối
khi hết phiên) thay vì connect → recv timeout 30s → reconnect vĩnh viễn.

#144: HOSE nghỉ trưa 11:30-13:00, nên "09:00-15:00" là hai phiên chứ không phải
một cửa sổ liền. Nghỉ trưa phải ngủ 90 phút, không reconnect mỗi 30s. Ngày lễ
được bỏ qua khi DNSE working-dates trả lịch phủ tới ngày đó; không có lịch thì
chỉ bỏ cuối tuần và ghi log (fail-open, không bỏ nhầm phiên).
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from opentrading_mcp import loops
from opentrading_mcp.loops import (
    VN_TZ,
    _parse_trading_days,
    _seconds_until_open,
    dnse_off_hours,
    dnse_session,
    dnse_window,
)


def vn(hour: int, minute: int = 0, day: int = 19) -> datetime:
    # 2026-10-19 is a Monday.
    return datetime(2026, 10, day, hour, minute, tzinfo=VN_TZ)


def test_window_is_9_to_15_same_day():
    start, end = dnse_window(vn(10, 30))
    assert (start.hour, start.minute) == (9, 0)
    assert (end.hour, end.minute) == (15, 0)
    assert start.day == end.day == 19


def test_active_at_open_boundary():
    assert dnse_off_hours(vn(9, 0)) is False


def test_active_mid_session():
    assert dnse_off_hours(vn(10, 30)) is False


def test_session_split_at_lunch_break():
    """#144: 09:00-11:30 and 13:00-15:00 are separate sessions."""
    morning = dnse_session(vn(10, 30))
    assert morning is not None
    assert (morning[0].hour, morning[0].minute) == (9, 0)
    assert (morning[1].hour, morning[1].minute) == (11, 30)
    afternoon = dnse_session(vn(14, 0))
    assert afternoon is not None
    assert (afternoon[0].hour, afternoon[0].minute) == (13, 0)
    assert (afternoon[1].hour, afternoon[1].minute) == (15, 0)


def test_lunch_break_is_off_hours():
    assert dnse_off_hours(vn(11, 29)) is False
    assert dnse_off_hours(vn(11, 30)) is True
    assert dnse_off_hours(vn(12, 0)) is True
    assert dnse_off_hours(vn(12, 59)) is True
    assert dnse_off_hours(vn(13, 0)) is False
    assert dnse_session(vn(12, 0)) is None


def test_lunch_break_sleeps_to_afternoon_open():
    assert _seconds_until_open(vn(11, 30)) == pytest.approx(90 * 60)
    assert _seconds_until_open(vn(12, 59)) == pytest.approx(60.0)
    assert _seconds_until_open(vn(11, 29)) == pytest.approx(0.0)


def test_active_before_close():
    assert dnse_off_hours(vn(14, 59)) is False


def test_off_at_close_boundary():
    assert dnse_off_hours(vn(15, 0)) is True


def test_off_early_morning_sleeps_to_same_day_open():
    assert dnse_off_hours(vn(8, 59)) is True
    assert _seconds_until_open(vn(8, 59)) == pytest.approx(60.0)


def test_off_evening_sleeps_to_next_day_open():
    assert dnse_off_hours(vn(23, 0)) is True
    assert _seconds_until_open(vn(23, 0)) == pytest.approx(10 * 3600.0)


def test_off_after_close_sleeps_to_next_day_open():
    assert dnse_off_hours(vn(15, 1)) is True
    # 15:01 → 09:00 hôm sau = 17h59m.
    assert _seconds_until_open(vn(15, 1)) == pytest.approx(17 * 3600 + 59 * 60)


def test_naive_datetime_is_interpreted_as_vn_time():
    naive = datetime(2026, 10, 19, 10, 30)
    assert dnse_off_hours(naive) is False


def test_loop_sleeps_until_open_when_off_hours(monkeypatch):
    """Ngoài giờ, dnse_ws_loop phải ngủ _seconds_until_open() chứ không connect."""
    monkeypatch.setenv("DNSE_API_KEY", "k")
    monkeypatch.setenv("DNSE_SECRET", "s")
    monkeypatch.setattr(loops, "dnse_off_hours", lambda now=None: True)
    monkeypatch.setattr(loops, "_seconds_until_open", lambda now=None, **kw: 42.0)

    async def no_calendar():  # keep the holiday calendar offline
        return None

    monkeypatch.setattr(loops, "_exchange_trading_days", no_calendar)
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        raise asyncio.CancelledError

    monkeypatch.setattr(loops.asyncio, "sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(loops.dnse_ws_loop())
    assert slept == [42.0]


def test_weekend_is_off_and_sleeps_to_monday_open():
    # Saturday 10:30 (inside 9-15h, but no session) → Monday 09:00 = 46h30m.
    assert dnse_off_hours(vn(10, 30, day=17)) is True
    assert _seconds_until_open(vn(10, 30, day=17)) == pytest.approx(46 * 3600 + 30 * 60)
    # Friday 15:01 → Monday 09:00 = 65h59m.
    assert _seconds_until_open(vn(15, 1, day=23)) == pytest.approx(65 * 3600 + 59 * 60)
    # Sunday 23:00 → Monday 09:00 = 10h.
    assert _seconds_until_open(vn(23, 0, day=18)) == pytest.approx(10 * 3600.0)


def test_holiday_is_skipped_when_calendar_covers_the_day():
    """A weekday absent from a calendar that reaches it is a holiday."""
    holiday = vn(8, 0, day=19)
    calendar = frozenset({"2026-10-20", "2026-10-21"})
    # Monday 08:00 holiday → Tuesday 09:00 = 25h.
    assert _seconds_until_open(holiday, trading_days=calendar) == pytest.approx(25 * 3600)
    # The opposite case: a trading day in the calendar is not skipped.
    assert _seconds_until_open(vn(8, 0, day=20), trading_days=calendar) == pytest.approx(3600)


def test_calendar_that_stops_before_the_day_does_not_skip_it():
    """A bounded/stale calendar must never cost a session (fail-open)."""
    stale = frozenset({"2026-10-01", "2026-10-02"})
    assert _seconds_until_open(vn(8, 0, day=19), trading_days=stale) == pytest.approx(3600)


def test_parse_trading_days_accepts_both_payload_shapes():
    payload = [{"date": "2026-10-19T00:00:00"}, "2026-10-20", {"date": ""}]
    assert _parse_trading_days(payload) == frozenset({"2026-10-19", "2026-10-20"})
    assert _parse_trading_days({"dates": [{"date": "2026-10-21"}]}) == frozenset({"2026-10-21"})
    assert _parse_trading_days(None) == frozenset()


def test_calendar_fetch_failure_falls_back_to_weekday_sleep(monkeypatch):
    """DNSE down must not break the loop: weekday-only sleep + one log line."""
    logs: list[str] = []
    monkeypatch.setattr(loops, "_log", logs.append)

    def boom() -> None:
        raise RuntimeError("dnse down")

    monkeypatch.setattr(loops.dnse_p, "working_dates", boom)
    assert asyncio.run(loops._exchange_trading_days()) is None
    assert any("weekday-only" in line for line in logs)
