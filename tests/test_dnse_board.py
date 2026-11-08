"""#84: batch quote from the project's DNSE client, in the v4 board shape.

Payloads are trimmed copies of the live DNSE answers for FPT captured on
2026-11-09 (after the 11-06 session). The expected numbers are the v4 (vnstock
4.0.2) baseline row for the same session — tests/fixtures/parity_v4_2026-11-08.
"""

from __future__ import annotations

import pytest

from opentrading_mcp.providers import dnse_board
from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable

TRADES = {"trades": [
    {"marketId": "STO", "boardId": "G1", "symbol": "FPT", "matchPrice": 50.8, "matchQtty": 20,
     "avgPrice": 51.179, "totalVolumeTraded": 1216220, "grossTradeAmount": 622.44945,
     "highestPrice": 51.8, "lowestPrice": 50.8, "openPrice": 51.4,
     "time": "2026-11-06 14:45:02.813"},
    {"marketId": "STO", "boardId": "T1", "symbol": "FPT", "matchPrice": 56.6,
     "totalVolumeTraded": 17000, "time": "2026-11-06 13:34:25.136"},
]}
SECDEF_NEXT = [{"marketId": "STO", "boardId": "G1", "symbol": "FPT", "basicPrice": 50.8,
                "ceilingPrice": 54.3, "floorPrice": 47.25, "time": "2026-11-06 20:26:12.760"}]
SECDEF_SAME = [{"marketId": "STO", "boardId": "G1", "symbol": "FPT", "basicPrice": 52.9,
                "ceilingPrice": 56.6, "floorPrice": 49.2, "time": "2026-11-05 20:26:00.000"}]
QUOTES = {"quotes": [{"marketId": "STO", "boardId": "G1", "symbol": "FPT",
                      "bid": [{"price": 50.8, "quantity": 12230},
                              {"price": 50.7, "quantity": 20210},
                              {"price": 50.6, "quantity": 13080}],
                      "offer": [{"price": 50.9, "quantity": 610}, {"price": 51, "quantity": 7710},
                                {"price": 51.1, "quantity": 1940}]}]}


def _prev_close(seen: list):
    def fn(symbol, day):
        seen.append((symbol, day))
        return 52900.0

    return fn


def test_off_hours_row_matches_the_v4_baseline():
    """After the close DNSE already publishes the NEXT session's secdef; the
    traded session's reference is then the previous close (v4: 52,900)."""
    seen: list = []
    row = dnse_board.build_row("FPT", SECDEF_NEXT, TRADES, QUOTES, _prev_close(seen))
    assert seen == [("FPT", "2026-11-06")]
    expected = {  # v4 baseline row, FPT 2026-11-06
        "reference_price": 52900, "open_price": 51400, "high_price": 51800, "low_price": 50800,
        "close_price": 50800, "average_price": 51179, "volume_accumulated": 12162200,
        "total_value": 622449450000, "price_change": -2100, "bid_price_1": 50800,
        "bid_vol_1": 122300, "ask_price_1": 50900, "ask_vol_1": 6100, "exchange": "HOSE",
    }
    for key, value in expected.items():
        assert row[key] == value, key
    assert row["percent_change"] == pytest.approx(-3.9698, abs=1e-4)
    assert row["ceiling_price"] is None and row["floor_price"] is None
    assert row["next_session"]["reference_price"] == 50800
    assert "market closed" in row["quote_note"]
    assert row["time"] == "2026-11-06T14:45:02.813+07:00"
    assert row["foreign_buy_volume"] is None  # no realtime source


def test_in_session_row_uses_secdef_limits():
    seen: list = []
    trades = {"trades": [{**TRADES["trades"][0], "time": "2026-11-06 10:00:00.000"}]}
    secdef = [{**SECDEF_SAME[0], "time": "2026-11-06 08:00:00.000"}]
    row = dnse_board.build_row("FPT", secdef, trades, QUOTES, _prev_close(seen))
    assert seen == []  # no candle lookup during the session
    assert (row["reference_price"], row["ceiling_price"], row["floor_price"]) == (
        52900, 56600, 49200)
    assert "quote_note" not in row and "next_session" not in row


def test_row_without_depth_still_has_prices():
    row = dnse_board.build_row("FPT", SECDEF_NEXT, TRADES, None, _prev_close([]))
    assert row["close_price"] == 50800
    assert row["bid_price_1"] is None and row["ask_vol_3"] is None


def test_no_main_board_trade_is_bad_data():
    with pytest.raises(ProviderBadData, match="main-board"):
        dnse_board.build_row("FPT", SECDEF_NEXT, {"trades": []}, QUOTES, _prev_close([]))


def test_index_codes_are_refused():
    with pytest.raises(ProviderBadData, match="vn_index_ohlcv"):
        dnse_board.quote_row("VNINDEX")


def test_failed_symbols_are_reported_not_dropped(monkeypatch):
    def fake_row(symbol):
        if symbol == "BAD":
            raise ProviderUnavailable("dnse timeout")
        return {"symbol": symbol, "close_price": 1.0}

    monkeypatch.setattr(dnse_board, "quote_row", fake_row)
    rows = dnse_board.quote_rows(["FPT", "BAD"])
    assert rows[0]["symbol"] == "FPT"
    assert rows[-1]["_missing"] == ["BAD"] and "timeout" in rows[-1]["_errors"]["BAD"]


def test_missing_dnse_keys_are_not_configured(monkeypatch):
    for var in ("DNSE_API_KEY", "DNSE_SECRET"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ProviderUnavailable) as info:
        dnse_board.quote_rows(["FPT", "VCB"])
    assert info.value.reason == "not_configured"


def test_vn30_basket_is_read_live_and_cached(monkeypatch):
    """The hard-coded VN30 had drifted 8/30 symbols; the live basket wins."""
    import sys
    import types

    from opentrading_mcp.providers import vnstock as vn_p

    live = [f"S{i:02d}" for i in range(30)]
    calls: list[str] = []

    class Frame:
        def to_dict(self, orient="records"):
            return [{"symbol": s} for s in live]

    class Reference:
        def __init__(self, source=None, **kw):
            calls.append(source)
            self.equity = types.SimpleNamespace(list_by_group=lambda group: Frame())

    monkeypatch.setitem(sys.modules, "vnstock", types.SimpleNamespace(Reference=Reference))
    monkeypatch.setattr(vn_p, "_vn30_cache", None)
    assert vn_p.vn30_symbols() == live
    assert vn_p.vn30_symbols() == live
    assert calls == ["ssi"]  # second call served from the 24 h cache


def test_vn30_falls_back_to_the_dated_list(monkeypatch):
    import sys
    import types

    from opentrading_mcp.providers import vnstock as vn_p

    class Reference:
        def __init__(self, *a, **k):
            raise RuntimeError("no key")

    monkeypatch.setitem(sys.modules, "vnstock", types.SimpleNamespace(Reference=Reference))
    monkeypatch.setattr(vn_p, "_vn30_cache", None)
    assert vn_p.vn30_symbols() == vn_p.VN30
    assert "PJB" not in vn_p.VN30 and "VRE" in vn_p.VN30  # the 2026-11-09 basket


async def test_batch_quote_tool_serves_dnse_rows(monkeypatch):
    from opentrading_mcp.providers import dnse
    from opentrading_mcp.server import create_server, register_preset

    payloads = {"/price/FPT/trades/latest": TRADES, "/price/FPT/secdef": SECDEF_NEXT,
                "/price/FPT/quotes/latest": QUOTES}
    monkeypatch.setattr(dnse, "_get", lambda path, params=None, timeout=20: payloads[path])
    monkeypatch.setattr(dnse_board, "_previous_close", lambda s, d: 52900.0)
    server = create_server("all")
    register_preset(server, "all")
    env = await server._tool_manager.get_tool("vn_equity_quote_batch").fn(symbols=["FPT"])
    rows = env["data"]["quotes"] if "quotes" in env["data"] else env["data"]["rows"]
    assert rows[0]["close_price"] == 50800 and rows[0]["percent_change"] < 0
