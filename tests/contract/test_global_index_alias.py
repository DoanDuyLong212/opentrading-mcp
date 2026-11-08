"""Contract: global index aliasing → Yahoo tickers, informative errors (#78, #97).

vn_global_index moved from vnstock's fmp route (no key, MSN-style codes nobody
verified) to yfinance. Every alias target below was checked live on 2026-11-09
(^GSPC 7376.86, ^DJI 51285.73, ^NDX 26989.99, …); the old MSN codes stay
accepted so existing callers keep working.
"""

from __future__ import annotations

import sys
import types

import pandas as pd
import pytest

from opentrading_mcp.providers import yfinance as yf_p
from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable

norm = yf_p.normalize_global_symbol


@pytest.mark.parametrize(
    ("spelling", "ticker"),
    [
        ("SPX", "^GSPC"), ("S&P 500", "^GSPC"), ("^GSPC", "^GSPC"),
        ("Dow Jones", "^DJI"), ("DJI", "^DJI"),
        ("Nasdaq", "^IXIC"), ("Nasdaq Composite", "^IXIC"), ("NDX", "^NDX"),
        ("CAC 40", "^FCHI"), ("FTSE100", "^FTSE"), ("Nikkei 225", "^N225"),
        ("HangSeng", "^HSI"), ("SHCOMP", "000001.SS"), ("000001.SS", "000001.SS"),
        (" ^gdaxi ", "^GDAXI"), ("SENSEX", "^BSESN"),
    ],
)
def test_common_spellings_map_to_yahoo(spelling, ticker):
    assert norm(spelling) == ticker


@pytest.mark.parametrize(
    ("old_code", "ticker"),
    [("INX", "^GSPC"), ("USA30", "^DJI"), ("COMP", "^IXIC"), ("UKX", "^FTSE"),
     ("PX1", "^FCHI"), ("N225", "^N225"), ("000001", "000001.SS")],
)
def test_old_msn_codes_still_work(old_code, ticker):
    assert norm(old_code) == ticker


@pytest.mark.parametrize("spelling", ["VNI", "VN-Index", "VNINDEX"])
def test_vn_index_points_to_the_domestic_route(spelling):
    with pytest.raises(ProviderBadData, match="vn_index_ohlcv"):
        norm(spelling)


def test_unknown_symbol_lists_valid_codes():
    with pytest.raises(ProviderBadData) as info:
        norm("NOT-AN-INDEX")
    assert "S&P 500" in str(info.value) and "NDX" in str(info.value)


def test_other_yahoo_index_tickers_pass_through():
    assert norm("^STOXX50E") == "^STOXX50E"


def _install_yahoo(monkeypatch, frame: pd.DataFrame, seen: dict):
    class Ticker:
        def __init__(self, ticker):
            seen["ticker"] = ticker

        def history(self, **kw):
            seen.update(kw)
            return frame

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=Ticker))


def _frame(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2026-11-02", periods=len(closes), freq="D", tz="America/New_York")
    return pd.DataFrame(
        {"Open": closes, "High": closes, "Low": closes, "Close": closes,
         "Volume": [1.0] * len(closes)},
        index=idx,
    )


def test_global_index_reaches_yahoo_with_the_mapped_ticker(monkeypatch):
    seen: dict = {}
    _install_yahoo(monkeypatch, _frame([1.0, float("nan"), 3.0, 4.0]), seen)
    from opentrading_mcp.providers import circuit

    circuit.reset("yfinance")
    rows = yf_p.global_index("SPX", 2)
    assert seen["ticker"] == "^GSPC" and seen["interval"] == "1d"
    assert [r["close"] for r in rows] == [3.0, 4.0]  # NaN close dropped, last `count`
    assert rows[0]["time"] == "2026-11-04"
    assert set(rows[0]) == {"time", "open", "high", "low", "close", "volume"}


def test_float32_noise_is_rounded_to_its_real_precision(monkeypatch):
    """Yahoo sends float32 prices: 7678.72021484375 is 7678.72, and an FX rate
    such as 1.1228 must keep its decimals."""
    seen: dict = {}
    frame = _frame([7678.72021484375])
    frame["Volume"] = [7654840000.0]
    _install_yahoo(monkeypatch, frame, seen)
    assert yf_p.global_index("SPX", 1)[0]["close"] == 7678.72
    assert yf_p.global_index("SPX", 1)[0]["volume"] == 7654840000.0
    _install_yahoo(monkeypatch, _frame([1.122799992561340332]), seen)
    assert yf_p.fx_history("EURUSD", 1)[0]["close"] == 1.1228


def test_empty_yahoo_frame_is_unavailable(monkeypatch):
    _install_yahoo(monkeypatch, pd.DataFrame(), {})
    with pytest.raises(ProviderUnavailable, match="no bars"):
        yf_p.global_index("SPX", 5)


def test_docstring_lists_symbols():
    from opentrading_mcp.server import create_server, register_all

    server = create_server()
    register_all(server)
    text = server._tool_manager.get_tool("vn_global_index").fn.__doc__ or ""
    for marker in ("S&P 500", "Dow Jones", "NDX", "vn_index_ohlcv"):
        assert marker in text, f"docstring missing {marker!r}"
