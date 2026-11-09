"""financeinfo pages share ONE Vietstock login with every Vietstock tool, and
stock_screener fans out over many symbols (3 pages each for a quarterly read).
Process-wide: at most FINANCEINFO_CONCURRENCY pages in flight, starts at least
FINANCEINFO_MIN_GAP_S apart."""

from __future__ import annotations

import itertools
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from opentrading_mcp.providers import vietstock as vs_p


@pytest.fixture
def fake_post(monkeypatch):
    state = {"live": 0, "peak": 0, "starts": []}
    lock = threading.Lock()

    def post(path, body):
        assert path == "/data/financeinfo"
        with lock:
            state["live"] += 1
            state["peak"] = max(state["peak"], state["live"])
            state["starts"].append(time.monotonic())
        time.sleep(0.03)
        with lock:
            state["live"] -= 1
        return {"page": body["Page"]}

    monkeypatch.setattr(vs_p, "_post", post)
    monkeypatch.setattr(vs_p, "FINANCEINFO_MIN_GAP_S", 0.02)
    monkeypatch.setattr(vs_p, "_financeinfo_last_start", 0.0)
    return state


def test_a_screener_burst_never_exceeds_two_pages_in_flight(fake_post):
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda s: vs_p.financeinfo(s, "quarter"), [f"S{i}" for i in range(12)]))
    assert len(fake_post["starts"]) == 36  # 12 symbols x 3 quarterly pages
    assert fake_post["peak"] <= vs_p.FINANCEINFO_CONCURRENCY == 2


def test_page_starts_are_spaced(fake_post):
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda s: vs_p.financeinfo(s, "year"), ["A", "B", "C", "D", "E"]))
    starts = sorted(fake_post["starts"])
    gaps = [b - a for a, b in itertools.pairwise(starts)]
    assert min(gaps) >= 0.02 * 0.9


def test_pages_keep_their_order_and_body(fake_post):
    out = vs_p.financeinfo("FPT", "quarter")
    assert [p["page"] for p in out["pages"]] == [1, 2, 3]


def test_production_limits_are_the_conservative_ones():
    assert vs_p.FINANCEINFO_CONCURRENCY == 2
    assert vs_p.FINANCEINFO_MIN_GAP_S == 0.5
