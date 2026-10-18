"""Unit tests for the DNSE WS market-window gate (offline, no network).

Ngoài 9-15h giờ Việt Nam, vòng lặp WS phải ngủ tới 09:00 (hoặc ngắt kết nối
khi chạm 15:00) thay vì connect → recv timeout 30s → reconnect vĩnh viễn
(churn ~17k dòng trong worker.log).
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from opentrading_mcp import loops
from opentrading_mcp.loops import VN_TZ, _seconds_until_open, dnse_off_hours, dnse_window


def vn(hour: int, minute: int = 0, day: int = 18) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=VN_TZ)


def test_window_is_9_to_15_same_day():
    start, end = dnse_window(vn(10, 30))
    assert (start.hour, start.minute) == (9, 0)
    assert (end.hour, end.minute) == (15, 0)
    assert start.day == end.day == 18


def test_active_at_open_boundary():
    assert dnse_off_hours(vn(9, 0)) is False


def test_active_mid_session():
    assert dnse_off_hours(vn(10, 30)) is False


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
    naive = datetime(2026, 10, 18, 10, 30)
    assert dnse_off_hours(naive) is False


def test_loop_sleeps_until_open_when_off_hours(monkeypatch):
    """Ngoài giờ, dnse_ws_loop phải ngủ _seconds_until_open() chứ không connect."""
    monkeypatch.setenv("DNSE_API_KEY", "k")
    monkeypatch.setenv("DNSE_SECRET", "s")
    monkeypatch.setattr(loops, "dnse_off_hours", lambda now=None: True)
    monkeypatch.setattr(loops, "_seconds_until_open", lambda now=None: 42.0)
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        raise asyncio.CancelledError

    monkeypatch.setattr(loops.asyncio, "sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(loops.dnse_ws_loop())
    assert slept == [42.0]
