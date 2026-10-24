"""A new rally attempt after a failed one is reported; dates are ISO.

Fixture: live VNINDEX daily bars to 2026-10-22. Day 1 on 16/10 failed on 19/10
(close 1689.84 under the 1694.77 low); 20/10 made a lower low (1677.19), then
21/10 (+2.76%) started a new attempt and 22/10 rose again. The tool still said
"failed" with Day 1 = 16/10.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from mcp.server.fastmcp import FastMCP

import opentrading_mcp.tools.market_timing as mt
from opentrading_mcp.schemas import make_envelope

BARS: list[dict[str, Any]] = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "vnindex_1d_20261022.json").read_text(
        encoding="utf-8"
    )
)["bars"]


def test_new_attempt_after_a_failure_is_the_latest_state():
    closes, volumes, lows, dates = mt._series(BARS)
    out = mt._follow_through(closes, volumes, lows, dates)
    assert out["state"] == "rally_attempt"
    assert out["day1_date"] == "2026-10-21"
    assert out["day1_low"] == 1677.19
    assert out["days_since_day1"] == 1
    assert out["last_failed"] == {
        "day1_date": "2026-10-16",
        "day1_low": 1694.77,
        "failed_date": "2026-10-19",
    }


def _row(day: int, close: float, volume: float) -> dict[str, Any]:
    return {"time": f"2026-03-{day:02d}", "close": close, "volume": volume, "low": close - 1}


def test_confirmed_attempt_stays_confirmed_on_later_up_days():
    closes = [100, 98, 96, 94, 95, 95.5, 96, 97.6, 98, 98.5, 99]
    volumes = [10, 10, 10, 10, 10, 9, 9, 20, 9, 9, 9]
    rows = [_row(i + 1, c, v) for i, (c, v) in enumerate(zip(closes, volumes, strict=True))]
    out = mt._follow_through(*mt._series(rows))
    assert out["state"] == "confirmed"
    assert out["day1_date"] == "2026-03-05"
    assert out["ftd_date"] == "2026-03-08"  # Day 4, +1.67% on higher volume
    assert "last_failed" not in out


def test_failure_without_a_new_attempt_stays_failed():
    closes, volumes, lows, dates = mt._series(BARS[:-2])  # up to 20/10
    out = mt._follow_through(closes, volumes, lows, dates)
    assert out["state"] == "failed"
    assert out["day1_date"] == "2026-10-16"
    assert "last_failed" not in out


def test_intraday_low_break_invalidates_even_when_close_recovers_and_volume_confirms():
    # Day 4 qualifies by close and volume, but its low breaks the Day 1 floor.
    closes = [100, 98, 96, 94, 95, 95.5, 96, 98]
    lows = [99, 97, 95, 93, 94, 94.5, 95, 92.9]
    volumes = [10, 10, 10, 10, 10, 10, 10, 20]
    dates = [f"2026-03-{i:02d}" for i in range(1, 9)]
    out = mt._follow_through(closes, volumes, lows, dates)
    assert out["state"] == "failed"
    assert out["day1_date"] == dates[4]
    assert out["day1_low"] == 93
    assert out["ftd_date"] is None
    assert "last_failed" not in out


def test_break_bar_cannot_be_new_day1_or_ftd_then_equality_can_start_attempt():
    closes = [100, 98, 96, 94, 95, 97, 98, 99, 100]
    lows = [99, 97, 95, 93, 94, 92, 92, 92, 92]
    volumes = [10, 10, 10, 10, 10, 20, 10, 10, 10]
    dates = [f"2026-03-{i:02d}" for i in range(1, 10)]
    # Break on day 6, despite strong upward close; day 7 starts the next attempt.
    failed = mt._follow_through(closes[:6], volumes[:6], lows[:6], dates[:6])
    assert failed["state"] == "failed"
    assert failed["day1_date"] == dates[4]
    next_attempt = mt._follow_through(closes, volumes, lows, dates)
    assert next_attempt["state"] == "rally_attempt"  # no Day 2/3 FTD
    assert next_attempt["day1_date"] == dates[6]
    assert next_attempt["day1_low"] == 92
    assert next_attempt["last_failed"]["failed_date"] == dates[5]


def test_confirmed_attempt_later_intraday_break_fails_even_if_close_is_higher():
    closes = [100, 98, 96, 94, 95, 95.5, 96, 97.6, 99]
    lows = [99, 97, 95, 93, 94, 94, 95, 95, 92.9]
    volumes = [10, 10, 10, 10, 10, 9, 9, 20, 30]
    dates = [f"2026-03-{i:02d}" for i in range(1, 10)]
    assert mt._follow_through(closes[:8], volumes[:8], lows[:8], dates[:8])["state"] == "confirmed"
    out = mt._follow_through(closes, volumes, lows, dates)
    assert out["state"] == "failed"
    assert out["ftd_date"] == dates[7]
    assert out["day1_low"] == 93


@pytest.mark.parametrize(
    "bad_fields",
    [
        {"close": float("nan")}, {"close": float("inf")},
        {"volume": float("nan")}, {"volume": float("inf")},
        {"low": float("nan")}, {"low": float("-inf")},
        {"low": 0}, {"low": 101},
        {"high": float("inf")}, {"high": 99},
        {"open": float("nan")}, {"open": 98},
        {"open": 102, "high": 101},
    ],
)
def test_invalid_candle_cannot_enter_timing_state(bad_fields):
    rows = [_row(i + 1, 100, 10) for i in range(6)]
    rows[-1].update(bad_fields)
    assert mt._series(rows) is None


async def test_first_ftd_date_is_permanent_reset_anchor(monkeypatch):
    closes = [100, 98, 96, 94, 95, 95.5, 96, 97.6, 97.2, 99, 98.5]
    volumes = [10, 10, 10, 10, 10, 9, 9, 20, 21, 22, 23]
    rows = [_row(i + 1, c, v) for i, (c, v) in enumerate(zip(closes, volumes, strict=True))]
    parsed = mt._series(rows)
    assert parsed is not None
    ftd = mt._follow_through(*parsed)
    assert ftd["state"] == "confirmed"
    assert ftd["ftd_date"] == "2026-03-08"
    assert ftd["days_since_day1"] == 6

    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return rows

    async def no_cache(_tool: str, _fp: str) -> None:
        return None

    async def return_envelope(_tool: str, _fp: str, _ttl: int, data: Any, **meta: Any) -> Any:
        return make_envelope(data, **meta)

    monkeypatch.setattr(mt, "run_blocking", fake_block)
    monkeypatch.setattr(mt, "cache_lookup", no_cache)
    monkeypatch.setattr(mt, "cache_store", return_envelope)
    monkeypatch.setattr(mt, "in_vn_session", lambda: False)
    server = FastMCP("t")
    mt.register_market_timing_tools(server)
    env = await server._tool_manager.get_tool("distribution_count").fn(symbol="VNINDEX")
    assert env["data"]["ftd"]["ftd_date"] == "2026-03-08"
    assert env["data"]["reset_on_ftd"] is True
    assert [d["date"] for d in env["data"]["distribution_days"]] == [
        "2026-03-09", "2026-03-11"
    ]


async def test_tool_reports_iso_dates(monkeypatch):
    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return [dict(b) for b in BARS]

    monkeypatch.setattr(mt, "run_blocking", fake_block)
    monkeypatch.setattr(mt, "in_vn_session", lambda: False)
    async def no_cache(_tool: str, _fp: str) -> None:
        return None

    async def return_envelope(_tool: str, _fp: str, _ttl: int, data: Any, **meta: Any) -> Any:
        return make_envelope(data, **meta)

    monkeypatch.setattr(mt, "cache_lookup", no_cache)
    monkeypatch.setattr(mt, "cache_store", return_envelope)
    server = FastMCP("t")
    mt.register_market_timing_tools(server)
    env = await server._tool_manager.get_tool("distribution_count").fn(symbol="VNINDEX")
    data = env["data"]
    assert data["ftd"]["state"] == "rally_attempt"
    assert all(len(d["date"]) == 10 for d in data["distribution_days"])
    assert env["provenance"]["data_time"] == "2026-10-22"


async def test_tool_excludes_current_session_bar(monkeypatch):
    today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat()
    partial = dict(BARS[-1], t=f"{today}T00:00:00", c=1900, l=1600, v=100000)

    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return [*BARS, partial]

    async def no_cache(_tool: str, _fp: str) -> None:
        return None

    async def return_envelope(_tool: str, _fp: str, _ttl: int, data: Any, **meta: Any) -> Any:
        return make_envelope(data, **meta)

    monkeypatch.setattr(mt, "run_blocking", fake_block)
    monkeypatch.setattr(mt, "in_vn_session", lambda: True)
    monkeypatch.setattr(mt, "cache_lookup", no_cache)
    monkeypatch.setattr(mt, "cache_store", return_envelope)
    server = FastMCP("t")
    mt.register_market_timing_tools(server)
    env = await server._tool_manager.get_tool("distribution_count").fn(symbol="VNINDEX")
    assert env["provenance"]["data_time"] == "2026-10-22"
    assert "bỏ nến hôm nay vì phiên chưa đóng cửa" in env["warnings"]
