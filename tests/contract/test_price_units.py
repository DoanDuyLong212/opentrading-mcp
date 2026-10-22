"""Price results say their unit (OpenTrading BUG-OT-20261016-004).

vnstock candles are in thousand dong and the price board in dong; without a
unit a client wrote "62,2 (đ)" for 62.2 thousand dong.
"""

from __future__ import annotations

from typing import Any

from opentrading_mcp.server import create_server, register_all
from opentrading_mcp.units import UNITS, UNITS_KEY, with_units

CANDLES = [
    {"t": "2026-10-20", "o": 64.27, "h": 66.27, "l": 64.27, "c": 66.0, "v": 10189497.0},
    {"t": "2026-10-21", "o": 66.0, "h": 66.09, "l": 65.64, "c": 65.64, "v": 3557606.0},
]
BOARD = [
    {
        "symbol": "VCB",
        "reference_price": 56600,
        "close_price": 56700,
        "volume_accumulated": 3049500,
        "total_value": 172358200000,
        "percent_change": 0.18,
    }
]


def _server():
    server = create_server()
    register_all(server)
    return server


def test_every_unit_entry_names_a_registered_tool():
    names = {t.name for t in _server()._tool_manager.list_tools()}
    assert set(UNITS) <= names, sorted(set(UNITS) - names)


async def test_candles_say_thousand_dong_and_the_board_says_dong(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    monkeypatch.setattr(vn_p, "quote_history", lambda *a, **k: list(CANDLES))
    monkeypatch.setattr(vn_p, "equity_quote_batch", lambda *a, **k: [dict(r) for r in BOARD])
    server = _server()

    tool = server._tool_manager.get_tool("vn_quote_history")
    history = await tool.run({"symbol": "FPT", "days": 2})
    assert next(iter(history)) == UNITS_KEY
    assert "nghìn đồng" in history[UNITS_KEY]["o, h, l, c, last, high, low"]
    assert history["data"]["candles"][0]["c"] == 66.0

    board = await server._tool_manager.get_tool("vn_equity_quote_batch").run({"symbols": ["VCB"]})
    price_unit = next(u for k, u in board[UNITS_KEY].items() if "close_price" in k)
    assert price_unit.startswith("đồng")


def test_with_units_leaves_other_results_alone():
    env: dict[str, Any] = {"data": {"x": 1}, "provenance": {}}
    assert with_units("web_search", env) is env
    assert with_units("vn_quote_history", "plain text") == "plain text"
    already = {"units": {"c": "USD"}, "data": {}}
    assert with_units("vn_quote_history", already) is already
