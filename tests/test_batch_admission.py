"""Batch quotes larger than three chunks (found 2026-11-09 in session).

``equity_quote_batch`` admits three 10-symbol chunks at a time (P05). Chunks 4+
were dropped to ``missing`` at once instead of waiting for this batch's own legs:
``market_movers(universe="hose")`` (60 symbols) always lost 30 of them. The HOSE
listing also fed covered warrants into the movers universe.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.tools.market import _is_stock


@pytest.fixture
def board(monkeypatch):
    from opentrading_mcp.providers import dnse_board

    calls: list[list[str]] = []

    def rows(chunk):
        calls.append(list(chunk))
        time.sleep(0.05)
        return [{"symbol": s, "close_price": 1.0} for s in chunk]

    monkeypatch.setattr(vn_p, "SRC_QUOTE", ())
    monkeypatch.setattr(dnse_board, "quote_rows", rows)
    monkeypatch.setattr(vn_p, "_VN_BATCH_POOL", ThreadPoolExecutor(max_workers=3))
    monkeypatch.setattr(vn_p, "_VN_BATCH_SLOTS", threading.BoundedSemaphore(3))
    return calls


def test_sixty_symbols_all_come_back(board):
    syms = [f"S{i:02d}" for i in range(60)]
    rows = vn_p.equity_quote_batch.__wrapped__(syms)
    quotes, missing = vn_p.split_batch(rows)
    assert missing == []
    assert sorted(r["symbol"] for r in quotes) == syms
    assert len(board) == 6


def test_slots_held_by_others_still_fail_fast(board, monkeypatch):
    slots = threading.BoundedSemaphore(3)
    for _ in range(3):
        slots.acquire()  # three hung legs of earlier calls
    monkeypatch.setattr(vn_p, "_VN_BATCH_SLOTS", slots)
    t0 = time.monotonic()
    with pytest.raises(vn_p.ProviderUnavailable):
        vn_p.equity_quote_batch.__wrapped__(["AAA", "BBB"])
    assert time.monotonic() - t0 < 0.5
    assert board == []


def test_movers_universe_keeps_shares_only():
    rows = [
        {"symbol": "AAA", "type": "stock"},
        {"symbol": "CACB2515", "type": "warrant"},
        {"symbol": "E1VFVN30", "type": "etf"},
        {"symbol": "FUCVREIT", "type": "fund_certificate"},
        {"symbol": "AMY", "type": None},
        {"symbol": "FUEVCDIV", "type": None},
        {"symbol": "VN100", "type": None},
    ]
    assert [r["symbol"] for r in rows if _is_stock(r)] == ["AAA", "AMY"]
