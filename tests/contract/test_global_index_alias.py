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


async def test_global_index_alias_reaches_vnstock(monkeypatch):
    seen: dict[str, Any] = {}

    class FakeMarket:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def index(self, symbol: str, scope: str):
            seen["symbol"] = symbol
            return self

        def ohlcv(self, count: int):
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

    def fake_market():
        return FakeMarket()

    import importlib

    vnstock_mod = importlib.import_module("vnstock")
    monkeypatch.setattr(vnstock_mod, "Market", fake_market, raising=False)
    rows = vn_p.global_index("SPX", 5)
    assert seen["symbol"] == "INX"
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
