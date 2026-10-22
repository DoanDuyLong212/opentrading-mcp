"""distribution_count: closed sessions only, provenance, neutral wording."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import FastMCP

import opentrading_mcp.tools.market_timing as mt


def _tool():
    server = FastMCP("t")
    mt.register_market_timing_tools(server)
    return server._tool_manager.get_tool("distribution_count").fn


def _bars(last_day: date, n: int = 40) -> list[dict[str, Any]]:
    """Gently rising index; the last bar is a distribution day (-1% on higher volume)."""
    rows = []
    close, volume = 1000.0, 100.0
    for i in range(n):
        day = last_day - timedelta(days=n - 1 - i)
        if i == n - 1:
            close, volume = close * 0.99, volume * 2
        else:
            close, volume = close * 1.001, 100.0
        row = {"time": f"{day.isoformat()} 00:00:00", "close": close, "volume": volume}
        rows.append({**row, "low": close * 0.99})
    return rows


def _patch(monkeypatch, rows, in_session: bool):
    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return rows

    monkeypatch.setattr(mt, "run_blocking", fake_block)
    monkeypatch.setattr(mt, "in_vn_session", lambda: in_session)


async def test_open_session_bar_is_not_counted(monkeypatch):
    today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    _patch(monkeypatch, _bars(today), in_session=True)
    env = await _tool()(symbol="VNINDEX", days=40)
    assert env["data"]["count_25"] == 0
    assert any("chưa đóng cửa" in w for w in env["warnings"])
    assert env["provenance"]["data_time"].startswith((today - timedelta(days=1)).isoformat())


async def test_closed_session_bar_is_counted(monkeypatch):
    today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    _patch(monkeypatch, _bars(today), in_session=False)
    env = await _tool()(symbol="VNINDEX", days=40)
    assert env["data"]["count_25"] == 1
    assert env["provenance"]["data_time"].startswith(today.isoformat())
    assert not any("chưa đóng cửa" in w for w in env["warnings"])


def test_levels_describe_the_market_and_never_instruct():
    seen = set()
    for count in range(0, 8):
        key, text = mt._status(count)
        seen.add(key)
        assert "O'Neil" in text
        for word in ("nên thoát", "thoát", "mua đuổi", "cắt lỗ", "nên bán"):
            assert word not in text.lower(), (count, text)
    assert seen == {"binh_thuong", "quan_sat", "canh_bao", "canh_bao_cao", "nguy_hiem"}
