"""#79: vn_msn_fx_gold via yfinance — USD/VND plus gold labelled as FUTURES.

Yahoo has no spot gold (XAUUSD=X and XAU=X are empty, checked 2026-11-09), so
the gold leg is COMEX GC=F; it must say so instead of posing as spot XAUUSD.
"""

from __future__ import annotations

import pytest

from opentrading_mcp.providers import yfinance as yf_p
from opentrading_mcp.providers.errors import ProviderBadData


@pytest.fixture
def fake_history(monkeypatch):
    calls: list[tuple[str, int]] = []

    def history(ticker, count=30):
        calls.append((ticker, count))
        close = 25580.0 if ticker == "VND=X" else 4074.9
        return [{"time": "2026-11-06", "open": close, "high": close, "low": close,
                 "close": close, "volume": 0.0}]

    monkeypatch.setattr(yf_p, "history", history)
    return calls


def test_default_returns_both_legs_with_honest_labels(fake_history):
    out = {leg["symbol"]: leg for leg in yf_p.fx_gold()}
    assert set(out) == {"USDVND", "GC=F"}
    gold = out["GC=F"]
    assert gold["instrument"] == "futures" and gold["ticker"] == "GC=F"
    assert "NOT spot" in gold["note"] and gold["unit"] == "USD per troy ounce"
    assert out["USDVND"]["ticker"] == "VND=X" and out["USDVND"]["instrument"] == "spot_fx"
    assert out["USDVND"]["last"]["close"] == 25580.0


@pytest.mark.parametrize("spelling", ["XAUUSD", "gold", "GC", "gc=f"])
def test_gold_spellings_select_the_futures_leg(fake_history, spelling):
    out = yf_p.fx_gold([spelling])
    assert [leg["symbol"] for leg in out] == ["GC=F"]
    assert fake_history == [("GC=F", 35)]


def test_unknown_symbols_are_refused_not_dropped(fake_history):
    """v4 used to return [] for ['EURUSD'] and the tool then said 'empty'."""
    with pytest.raises(ProviderBadData, match="vn_forex_ohlcv"):
        yf_p.fx_gold(["EURUSD"])
    assert fake_history == []


@pytest.mark.parametrize(
    ("pair", "ticker"),
    [("USDVND", "USDVND=X"), ("eurusd", "EURUSD=X"), ("USD/VND", "USDVND=X"),
     ("USDVND=X", "USDVND=X")],
)
def test_fx_history_builds_the_yahoo_ticker(fake_history, pair, ticker):
    yf_p.fx_history(pair, 5)
    assert fake_history == [(ticker, 5)]


@pytest.mark.parametrize("pair", ["USD", "VNINDEX", "US-DOLLAR"])
def test_fx_history_rejects_non_pairs(fake_history, pair):
    with pytest.raises(ProviderBadData, match="six letters"):
        yf_p.fx_history(pair, 5)


async def test_tool_envelope_names_yfinance_and_carries_labels(fake_history):
    from opentrading_mcp.server import create_server, register_preset

    server = create_server("all")
    register_preset(server, "all")
    env = await server._tool_manager.get_tool("vn_msn_fx_gold").fn()
    assert env["provenance"]["source"] == "yfinance"
    legs = {leg["symbol"]: leg for leg in env["data"]["series"]}
    assert legs["GC=F"]["instrument"] == "futures"
    doc = server._tool_manager.get_tool("vn_msn_fx_gold").fn.__doc__ or ""
    assert "FUTURES" in doc and "via MSN" not in doc
