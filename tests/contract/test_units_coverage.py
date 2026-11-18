"""#138/#139: every tool that returns a price or money amount publishes `units`.

The envelope's first key is `units` so a client that cuts a long result still
sees it. A scale that was not measured is not guessed: the entry says
"chưa xác minh" (unverified) or names the mixture, and a test keeps that honest.
"""

from __future__ import annotations

import pytest

from opentrading_mcp.units import DONG, THOUSAND_DONG, UNITS, with_units

# #138 (raw DNSE/Vietstock/board) + #139 (derived tools).
REQUIRED = {
    "dnse_ohlc_history",
    "dnse_latest_trade",
    "dnse_orderbook",
    "dnse_foreign_flow",
    "dnse_ws_snapshot",
    "vs_market_price",
    "vs_trading_info",
    "vs_overview_trading",
    "breadth_scan",
    "valuation_run",
    "stock_overview",
    "peer_compare",
    "signals_technical",
    "stock_screener",
    "money_flow",
    "quant_backtest",
    "quant_risk",
    "quant_factors",
    "block_trades",
    "analyst_consensus",
    "dividends_splits",
}

# Entries that must admit a mixture or an unmeasured scale, never a bare guess.
# stock_screener left the list on 2026-11-18: its pe (current_ttm/period_end) and
# market_cap (Vietstock tradinginfo, VND) scales are now measured and published.
MUST_ADMIT = {
    "dnse_latest_trade",
    "dnse_orderbook",
    "dnse_foreign_flow",
    "dnse_ws_snapshot",
    "vs_market_price",
    "vs_overview_trading",
    "money_flow",
    "analyst_consensus",
}


def test_every_tool_has_a_units_entry() -> None:
    assert sorted(REQUIRED - set(UNITS)) == []


@pytest.mark.parametrize("tool", sorted(MUST_ADMIT))
def test_mixed_or_unmeasured_scales_say_so(tool: str) -> None:
    joined = " ".join(UNITS[tool].values()).lower()
    assert any(
        marker in joined
        for marker in ("chưa xác minh", "mixed", "đọc `unit`", "không trả", "không phải đồng")
    ), UNITS[tool]


def test_measured_scales_are_never_downgraded_to_guesses() -> None:
    assert UNITS["valuation_run"]["price"] == DONG
    assert UNITS["block_trades"]["close"] == DONG
    assert UNITS["block_trades"]["mt_val, pt_val"].startswith("đồng")
    assert UNITS["vs_trading_info"]["EPS, BVPS"].startswith("đồng")


def test_live_measured_scales_2026_11_18_stay_published() -> None:
    """The scales verified with a valid Vietstock JWT on 2026-11-18 (#138/#139)."""
    assert "USD" in UNITS["vs_market_price"]["Price, Change"]
    assert "nghìn đồng" in UNITS["dnse_ohlc_history"]["o, h, l, c, last, high, low"]
    assert UNITS["vs_overview_trading"]["_note"].startswith("TotalVol = cổ phiếu")
    assert "tỷ đồng" in UNITS["dnse_latest_trade"]["grossTradeAmount"]
    assert UNITS["peer_compare"]["p_e, p_b"].startswith("lần")
    backtest = UNITS["quant_backtest"]["gross_return, net_return, benchmark_return, max_drawdown"]
    assert "phân số" in backtest
    assert "phân số" in UNITS["quant_risk"]["max_drawdown, win_rate"]
    assert UNITS["dnse_ohlc_history"]["o, h, l, c, last, high, low"].startswith("điểm")
    assert THOUSAND_DONG in UNITS["dnse_latest_trade"]["matchPrice, openPrice, "
                                                        "highestPrice, lowestPrice, avgPrice"]


def test_units_are_the_first_key_of_the_envelope() -> None:
    envelope = {"data": {"price": 57400.0}, "provenance": {}, "warnings": []}
    out = with_units("valuation_run", envelope)
    assert next(iter(out)) == "units"
    assert out["units"] == UNITS["valuation_run"]


def test_units_keys_are_registered_tools() -> None:
    """A typo in UNITS would silently never publish."""
    from opentrading_mcp.server import create_server, register_all

    server = create_server()
    registered = {tool["name"] for tool in register_all(server)}
    assert sorted(set(UNITS) - registered) == []
