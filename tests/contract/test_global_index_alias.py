"""Contract: global index symbol aliasing + informative unknown-symbol error (Q69 fix)."""

from __future__ import annotations

from typing import Any

from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import ProviderUnavailable


def test_alias_maps_common_spellings():
    assert vn_p._normalize_global_symbol("SPX") == "INX"
    assert vn_p._normalize_global_symbol("GSPC") == "INX"
    assert vn_p._normalize_global_symbol("S&P500") == "INX"
    assert vn_p._normalize_global_symbol("^GSPC") == "INX"
    assert vn_p._normalize_global_symbol("DJI") == "USA30"  # vnstock treats DJI as USA30
    assert vn_p._normalize_global_symbol("Nasdaq") == "COMP"
    assert vn_p._normalize_global_symbol("IXIC") == "COMP"
    assert vn_p._normalize_global_symbol("CAC40") == "PX1"
    assert vn_p._normalize_global_symbol("FTSE100") == "UKX"
    assert vn_p._normalize_global_symbol("Nikkei") == "N225"
    assert vn_p._normalize_global_symbol("HangSeng") == "HSI"
    assert vn_p._normalize_global_symbol("SHCOMP") == "000001"
    # canonical codes pass through untouched
    for code in ("INX", "USA30", "COMP", "VNI", "SENSEX", "000001"):
        assert vn_p._normalize_global_symbol(code) == code


def test_alias_ignores_spaces_hyphens_and_dots():
    assert vn_p._normalize_global_symbol("S&P 500") == "INX"
    assert vn_p._normalize_global_symbol("Dow Jones") == "USA30"
    assert vn_p._normalize_global_symbol("Nasdaq Composite") == "COMP"
    assert vn_p._normalize_global_symbol("CAC 40") == "PX1"
    assert vn_p._normalize_global_symbol("CAC") == "PX1"
    assert vn_p._normalize_global_symbol("Nikkei 225") == "N225"
    assert vn_p._normalize_global_symbol("VN-Index") == "VNI"
    assert vn_p._normalize_global_symbol("000001.SS") == "000001"
    assert vn_p._normalize_global_symbol(" ^gdaxi ") == "DAX"


def test_aliases_and_listed_codes_exist_in_vnstock():
    # gen 6: the v4 msn const table is gone from the package — pin the accepted
    # codes to this frozen snapshot (recorded from the v4 table on 2026-11-08;
    # gen-6 global indices are fmp-served). Live re-verification goes through
    # scripts/parity_compare.py once an fmp key exists.
    frozen_v6_global_codes = {
        "INX", "USA30", "DJI", "COMP", "RUT", "NYA", "RUI", "RUA", "UKX", "DAX",
        "PX1", "N225", "000001", "HSI", "SENSEX", "VNI",
    }
    assert set(vn_p.GLOBAL_INDEX_ALIASES.values()) <= frozen_v6_global_codes
    listed = {
        code
        for part in vn_p.VALID_GLOBAL_SYMBOLS.split(", ")
        for code in part.split(" ")[0].split("/")
    }
    assert listed <= frozen_v6_global_codes, listed - frozen_v6_global_codes


async def test_global_index_alias_reaches_vnstock(monkeypatch):
    seen: dict[str, Any] = {}

    class FakeMarket:
        def __init__(self, source=None, **kwargs):
            seen["source"] = source

        def global_index(self, symbol: str):
            seen["symbol"] = symbol
            return self

        def ohlcv(self, *, count_back=None, interval=None, **kwargs):
            import pandas as pd

            return pd.DataFrame(
                [
                    {
                        "time": "2026-10-12",
                        "open": 1.0,
                        "high": 2.0,
                        "low": 0.5,
                        "close": 1.5,
                        "volume": 100,
                    }
                ]
            )

    import importlib

    vnstock_mod = importlib.import_module("vnstock")
    monkeypatch.setattr(vnstock_mod, "Market", FakeMarket, raising=False)
    # fmp was discontinued 2026-11-08 (global_index moves to yfinance, #78); re-enable
    # the old chain so the alias → upstream wiring stays tested until then.
    monkeypatch.setattr(vn_p, "SRC_GLOBAL", ("fmp",))
    rows = vn_p.global_index("SPX", 5)
    assert seen["symbol"] == "INX"
    assert seen["source"] == "fmp"
    assert rows and rows[-1]["close"] == 1.5


async def test_global_index_unknown_symbol_error_lists_valid(monkeypatch):
    import importlib

    vnstock_mod = importlib.import_module("vnstock")

    class FakeMarket:
        def index(self, symbol: str, scope: str):
            raise RuntimeError("bad symbol")

        def __call__(self):  # pragma: no cover
            return self

    def fake_market():
        return FakeMarket()

    monkeypatch.setattr(vnstock_mod, "Market", fake_market, raising=False)
    try:
        vn_p.global_index("NDX", 5)
        raise AssertionError("expected ProviderUnavailable")
    except ProviderUnavailable as exc:
        msg = str(exc)
        assert "NDX" in msg and "INX" in msg, msg
        assert "yf_global_indices" in msg, msg


def test_docstring_lists_symbols():
    from opentrading_mcp.server import create_server, register_all

    server = create_server()
    register_all(server)
    fn = server._tool_manager.get_tool("vn_global_index").fn
    text = fn.__doc__ or ""
    for marker in ("INX", "COMP", "USA30", "NDX"):
        assert marker in text, f"docstring missing {marker!r}"
