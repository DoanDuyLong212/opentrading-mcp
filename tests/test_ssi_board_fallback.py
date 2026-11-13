"""#118: Render cannot reach DNSE; board rows fall back to ssi candles."""

from __future__ import annotations

from typing import Any

import pytest

from opentrading_mcp.providers import circuit, dnse, dnse_board
from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import ProviderAuthMissing, ProviderUnavailable

CANDLES = [  # quote_history rows: thousand dong, shares
    {"t": "2026-11-11", "o": 21.3, "h": 21.4, "l": 21.1, "c": 21.3, "v": 15_000_000.0},
    {"t": "2026-11-12", "o": 21.3, "h": 21.35, "l": 21.05, "c": 21.05, "v": 14_696_900.0},
    {"t": "2026-11-13", "o": 21.05, "h": 21.2, "l": 21.0, "c": 21.05, "v": 9_460_100.0},
]


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(dnse_board, "_dnse_down_until", 0.0)
    for name in ("dnse", "ssi-board-fallback", "vnstock"):
        circuit.reset(name)
    yield
    for name in ("dnse", "ssi-board-fallback", "vnstock"):
        circuit.reset(name)


def _history(calls: list[str]):
    def history(symbol: str, days: int = 365, interval: str = "1D") -> list[dict[str, Any]]:
        calls.append(symbol)
        return CANDLES

    return history


def _dnse_timeout(calls: list[str]):
    def get(path: str, params: Any = None, timeout: int = 20) -> Any:
        calls.append(path)
        raise ProviderUnavailable(f"dnse timeout: {path}")

    return get


def test_unreachable_dnse_gives_a_reduced_ssi_row(monkeypatch):
    dnse_calls: list[str] = []
    monkeypatch.setattr(dnse, "_get", _dnse_timeout(dnse_calls))
    monkeypatch.setattr(vn_p.quote_history, "__wrapped__", _history([]))
    row = dnse_board.quote_row("hpg")
    assert row["source"] == "ssi-fallback"
    assert (row["symbol"], row["close_price"], row["reference_price"]) == ("HPG", 21050.0, 21050.0)
    assert (row["open_price"], row["high_price"], row["low_price"]) == (21050.0, 21200.0, 21000.0)
    assert row["volume_accumulated"] == 9_460_100
    assert row["price_change"] == 0.0 and row["percent_change"] == 0.0
    for key in ("ceiling_price", "floor_price", "bid_price_1", "ask_vol_3", "foreign_room"):
        assert row[key] is None, key
    assert "ex-rights" in row["quote_note"]


def test_after_one_failure_dnse_is_skipped_not_waited_on(monkeypatch):
    dnse_calls: list[str] = []
    monkeypatch.setattr(dnse, "_get", _dnse_timeout(dnse_calls))
    monkeypatch.setattr(vn_p.quote_history, "__wrapped__", _history([]))
    for sym in ("FPT", "VCB", "HPG", "SSI"):
        assert dnse_board.quote_row(sym)["source"] == "ssi-fallback"
    assert dnse_calls == ["/price/FPT/trades/latest"]  # one 20 s wait, not four


def test_open_dnse_breaker_falls_back(monkeypatch):
    def open_breaker(path: str, params: Any = None, timeout: int = 20) -> Any:
        raise circuit.CircuitOpenError("circuit 'dnse' is open", reason="upstream_down")

    monkeypatch.setattr(dnse, "_get", open_breaker)
    monkeypatch.setattr(vn_p.quote_history, "__wrapped__", _history([]))
    assert dnse_board.quote_row("FPT")["source"] == "ssi-fallback"


def test_missing_dnse_keys_do_not_fall_back(monkeypatch):
    def no_keys(path: str, params: Any = None, timeout: int = 20) -> Any:
        raise ProviderAuthMissing("DNSE_API_KEY not set")

    monkeypatch.setattr(dnse, "_get", no_keys)
    with pytest.raises(ProviderAuthMissing):
        dnse_board.quote_row("FPT")


def test_fallback_failures_never_open_the_vnstock_breaker(monkeypatch):
    def limited(symbol: str, days: int = 365, interval: str = "1D") -> Any:
        raise ProviderUnavailable("ssi rate limited")

    monkeypatch.setattr(dnse, "_get", _dnse_timeout([]))
    monkeypatch.setattr(vn_p.quote_history, "__wrapped__", limited)
    for _ in range(8):
        with pytest.raises(ProviderUnavailable):
            dnse_board.quote_row("FPT")
    # the shared candle breaker never counted them: candle tools keep working
    shared = circuit.get_circuit("vnstock")
    assert shared._failures == 0 and shared._opened_at is None
    monkeypatch.setattr(vn_p.quote_history, "__wrapped__", _history([]))
    with pytest.raises(ProviderUnavailable, match="ssi-board-fallback"):
        dnse_board.quote_row("FPT")  # its own breaker opened instead


def test_batch_rows_come_back_through_the_fallback(monkeypatch):
    monkeypatch.setattr(dnse, "_get", _dnse_timeout([]))
    monkeypatch.setattr(vn_p.quote_history, "__wrapped__", _history([]))
    rows = vn_p.equity_quote_batch(["FPT", "HPG", "VCB"])
    assert [r["symbol"] for r in rows] == ["FPT", "HPG", "VCB"]
    assert {r["source"] for r in rows} == {"ssi-fallback"}
