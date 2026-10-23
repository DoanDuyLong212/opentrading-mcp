"""A new rally attempt after a failed one is reported; dates are ISO.

Fixture: live VNINDEX daily bars to 2026-10-22. Day 1 on 16/10 failed on 19/10
(close 1689.84 under the 1694.77 low); 20/10 made a lower low (1677.19), then
21/10 (+2.76%) started a new attempt and 22/10 rose again. The tool still said
"failed" with Day 1 = 16/10.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

import opentrading_mcp.tools.market_timing as mt

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


async def test_tool_reports_iso_dates(monkeypatch):
    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return [dict(b) for b in BARS]

    monkeypatch.setattr(mt, "run_blocking", fake_block)
    monkeypatch.setattr(mt, "in_vn_session", lambda: False)
    server = FastMCP("t")
    mt.register_market_timing_tools(server)
    env = await server._tool_manager.get_tool("distribution_count").fn(symbol="VNINDEX")
    data = env["data"]
    assert data["ftd"]["state"] == "rally_attempt"
    assert all(len(d["date"]) == 10 for d in data["distribution_days"])
    assert env["provenance"]["data_time"] == "2026-10-22"
