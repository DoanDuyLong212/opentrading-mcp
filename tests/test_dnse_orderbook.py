"""dnse_orderbook depth from real DNSE ``/quotes/latest`` bodies captured in session
(2026-11-09 09:17). Before the fix the reader looked for top-level ``bids``/``asks``
and returned empty sides for every symbol."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from opentrading_mcp.providers import dnse
from opentrading_mcp.providers.dnse_board import order_book
from opentrading_mcp.providers.errors import ProviderUnavailable

FIX = Path(__file__).parent / "fixtures" / "dnse_quotes_2026-11-09"


def _body(name: str) -> Any:
    return json.loads((FIX / f"{name}_quotes_latest.json").read_text(encoding="utf-8"))


def test_hose_stock_depth_in_dong_and_shares() -> None:
    book = order_book(_body("FPT"), 3)
    assert book is not None
    assert book["board"] == "G1"
    # G1 row: bid 51 x 930 lots; the odd-lot G4 row (51.2 x 248) must not leak in.
    assert book["bids"][0] == {"price": 51000.0, "volume": 9300.0}
    assert book["asks"][0] == {"price": 51100.0, "volume": 5100.0}
    assert len(book["bids"]) == len(book["asks"]) == 3
    assert book["unit"] == "dong / shares"


def test_hnx_picks_g1_even_when_odd_lot_board_comes_first() -> None:
    body = _body("SHS")
    assert body["quotes"][0]["boardId"] == "G4"  # the captured order
    book = order_book(body, 10)
    assert book is not None
    assert book["bids"][0] == {"price": 13400.0, "volume": 123900.0}
    assert len(book["bids"]) == 10


def test_depth_is_clamped() -> None:
    assert len(order_book(_body("SHS"), 2)["asks"]) == 2  # type: ignore[index]
    assert len(order_book(_body("SHS"), 99)["asks"]) == 10  # type: ignore[index]
    assert len(order_book(_body("FPT"), 0)["asks"]) == 1  # type: ignore[index]


def test_futures_contract_is_not_scaled() -> None:
    book = order_book(_body("41I1GB000"), 3)
    assert book is not None
    assert book["bids"][0] == {"price": 1850.0, "volume": 15.0}
    assert book["unit"] == "index points / contracts"


def test_no_main_board_is_none() -> None:
    assert order_book({"quotes": []}) is None
    assert order_book(None) is None


def test_provider_reads_quotes_latest(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def fake_get(path: str, params: Any = None, timeout: int = 20) -> Any:
        seen.append(path)
        return _body("FPT")

    monkeypatch.setattr(dnse, "_get", fake_get)
    out = dnse.orderbook("fpt", 3)
    assert seen == ["/price/FPT/quotes/latest"]
    assert out["symbol"] == "FPT"
    assert out["bids"][0]["price"] == 51000.0


def test_provider_alias_without_book_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dnse, "_get", lambda path, params=None, timeout=20: {"quotes": []})
    with pytest.raises(ProviderUnavailable, match="contract code"):
        dnse.orderbook("VN30F1M")
