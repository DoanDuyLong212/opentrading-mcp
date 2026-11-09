"""Q1 (owner decision 2026-11-09): corporate events from the ssi market-wide
calendar, cached per year in the shared store. Rows are the live ssi answer for
FPT captured 2026-11-09."""

from __future__ import annotations

import threading
from datetime import date
from typing import Any

import pytest

from opentrading_mcp.providers import circuit, store
from opentrading_mcp.providers import events_calendar as ec
from opentrading_mcp.providers.errors import ProviderNoData

FPT_2026 = [
    {"symbol": "FPT", "event_title": "FPT - Phát hành cổ phiếu thưởng tỷ lệ 10%",
     "ex_right_date": "2026-09-21 07:00:00+07:00", "record_date": "2026-09-22 07:00:00+07:00",
     "payout_date": "NaT", "value": float("nan"), "ratio": 0.1,
     "issue_date": "2026-09-21 07:00:00+07:00", "event_type": "bonus_share",
     "ratio_text": None, "dividend_percent": 10.0, "exercise_price": float("nan")},
    {"symbol": "FPT",
     "event_title": "FPT - Trả cổ tức Đợt 2 năm 2025 bằng tiền 1000 đồng/cổ phiếu",
     "ex_right_date": "2026-05-28 07:00:00+07:00", "record_date": "2026-05-29 07:00:00+07:00",
     "payout_date": "NaT", "value": 1000.0, "ratio": float("nan"),
     "issue_date": "2026-06-10 07:00:00+07:00", "event_type": "cash_dividend",
     "ratio_text": None, "dividend_percent": 10.0, "exercise_price": float("nan")},
    {"symbol": "FPT", "event_title": "FPT - Tổ chức ĐHĐCĐ thường niên 2026",
     "ex_right_date": "2026-03-09 07:00:00+07:00", "record_date": "2026-03-10 07:00:00+07:00",
     "payout_date": "NaT", "value": float("nan"), "ratio": float("nan"),
     "issue_date": "2026-04-16 07:00:00+07:00", "event_type": "shareholder_meeting",
     "ratio_text": None, "dividend_percent": float("nan"), "exercise_price": float("nan")},
    {"symbol": "VCB", "event_title": "VCB - cổ tức", "ex_right_date": "2026-07-01 07:00:00+07:00",
     "record_date": None, "payout_date": None, "value": 400.0, "ratio": None,
     "issue_date": None, "event_type": "cash_dividend", "dividend_percent": 4.0,
     "exercise_price": None},
]


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    ec._years.clear()
    ec._failed_at.clear()
    ec._loading.clear()
    monkeypatch.setattr(store, "_memory", {})
    monkeypatch.setattr(store, "_redis", lambda: None)
    monkeypatch.setattr(ec, "_years_wanted", lambda today=None: [2026, 2025])
    from opentrading_mcp.providers import vnstock as vn_p

    monkeypatch.setattr(vn_p, "_source_ready", lambda source: True)
    yield
    ec._years.clear()
    ec._loading.clear()


def _fake_fetch(monkeypatch, by_year: dict[int, list[dict[str, Any]]]):
    calls: list[int] = []

    def fetch(year: int):
        calls.append(year)
        return [r for r in (ec.compact(x) for x in by_year.get(year, [])) if r is not None]

    monkeypatch.setattr(ec, "_fetch_year", fetch)
    return calls


def test_compact_keeps_dividends_and_issues_with_amounts():
    bonus, cash, meeting, _ = (ec.compact(r) for r in FPT_2026)
    assert meeting is None
    assert cash == {
        "symbol": "FPT", "event_type": "cash_dividend", "event_code": "DIV",
        "event_title_vi": "FPT - Trả cổ tức Đợt 2 năm 2025 bằng tiền 1000 đồng/cổ phiếu",
        "exright_date": "2026-05-28", "record_date": "2026-05-29",
        "payout_date": "2026-06-10", "value_per_share": 1000.0, "exercise_ratio": None,
        "dividend_percent": 10.0, "exercise_price": None,
    }
    assert bonus["event_code"] == "ISS" and bonus["exercise_ratio"] == 0.1
    assert bonus["value_per_share"] is None  # NaN never leaks out


def test_cold_cache_says_loading_and_starts_one_warm(monkeypatch):
    started = []
    monkeypatch.setattr(ec, "_warm_in_background", lambda delay_s=0.0: started.append(1) or True)
    with pytest.raises(ProviderNoData, match="still loading") as err:
        ec.events_for("FPT")
    assert err.value.retry_after_s == ec.RETRY_AFTER_S
    assert started == [1]


def test_loading_does_not_open_the_vnstock_breaker(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    circuit.reset("vnstock")
    monkeypatch.setattr(vn_p, "SRC_FUNDAMENTAL", ())
    monkeypatch.setattr(ec, "_warm_in_background", lambda delay_s=0.0: False)
    for _ in range(8):
        with pytest.raises(ProviderNoData):
            vn_p.corp_events("FPT")
    assert circuit.get_circuit("vnstock")._opened_at is None


def test_warm_then_serve_newest_first_and_filtered(monkeypatch):
    calls = _fake_fetch(monkeypatch, {2026: FPT_2026, 2025: []})
    ec.warm()
    assert calls == [2026, 2025]
    rows = ec.events_for("fpt", limit=5)
    assert [r["exright_date"] for r in rows] == ["2026-09-21", "2026-05-28"]
    ec.warm()
    assert calls == [2026, 2025]  # fresh years are not fetched again


def test_a_waking_instance_reads_the_shared_store(monkeypatch):
    _fake_fetch(monkeypatch, {2026: FPT_2026, 2025: []})
    ec.warm()
    ec._years.clear()  # a new process: memory empty, store (Redis) still holds the years
    calls = _fake_fetch(monkeypatch, {})
    assert [r["event_code"] for r in ec.events_for("FPT")] == ["ISS", "DIV"]
    assert calls == []


def test_store_ttl_is_a_day_for_this_year_and_a_week_for_last_year():
    today = date(2026, 11, 9)
    assert ec._ttl(2026, today) == 24 * 3600
    assert ec._ttl(2025, today) == 7 * 24 * 3600


def test_one_warm_thread_at_a_time(monkeypatch):
    gate = threading.Event()
    runs = []

    def slow_warm(years=None):
        runs.append(1)
        gate.wait(2)

    monkeypatch.setattr(ec, "warm", slow_warm)
    assert ec._warm_in_background() is True
    assert ec._warm_in_background() is False
    gate.set()


def test_fetch_failure_keeps_serving_what_is_loaded(monkeypatch):
    _fake_fetch(monkeypatch, {2026: FPT_2026})

    def boom(year):
        raise RuntimeError("ssi timeout")

    ec.warm([2026])
    monkeypatch.setattr(ec, "_fetch_year", boom)
    ec.warm([2025])  # logged, not raised
    monkeypatch.setattr(ec, "_warm_in_background", lambda delay_s=0.0: False)
    assert len(ec.events_for("FPT")) == 2  # 2025 still loading, 2026 served
    assert ec.coverage()["years"] == {"2026": "3 events", "2025": "loading"}


def test_without_ssi_keys_it_is_not_configured_not_loading(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p
    from opentrading_mcp.providers.errors import ProviderUnavailable

    monkeypatch.setattr(vn_p, "_source_ready", lambda source: False)
    started = []
    monkeypatch.setattr(ec, "_warm_in_background", lambda delay_s=0.0: started.append(1))
    with pytest.raises(ProviderUnavailable) as err:
        ec.events_for("FPT")
    assert err.value.reason == "not_configured" and not isinstance(err.value, ProviderNoData)
    assert started == []


def test_a_failed_year_is_not_refetched_for_ten_minutes(monkeypatch):
    calls = []

    def boom(year):
        calls.append(year)
        raise RuntimeError("HTTP 429 rate limited")

    monkeypatch.setattr(ec, "_fetch_year", boom)
    ec.warm([2026])
    ec.warm([2026])
    assert calls == [2026]
    monkeypatch.setitem(ec._failed_at, 2026, ec._failed_at[2026] - ec.RETRY_BACKOFF_S - 1)
    ec.warm([2026])
    assert calls == [2026, 2026]


async def test_loading_envelope_tells_clients_when_to_retry(monkeypatch):
    from opentrading_mcp.server import create_server, register_preset

    monkeypatch.setattr(ec, "_warm_in_background", lambda delay_s=0.0: False)
    srv = create_server("all")
    register_preset(srv, "all")
    env = await srv._tool_manager.get_tool("dividends_splits").fn(symbol="FPT", region="vn")
    assert env["availability"] == "unavailable"
    assert env["reason"] == "busy"
    assert env["retryable"] is True
    assert env["retry_after_s"] == ec.RETRY_AFTER_S


def test_store_entry_keeps_its_fetch_time(monkeypatch):
    _fake_fetch(monkeypatch, {2026: FPT_2026, 2025: []})
    ec.warm()
    ec._years.clear()
    import time as _time

    # the store entry is still there (its own TTL); a day later it must read as stale
    rows, stale = ec._rows_for(2026, now=_time.time() + ec.CURRENT_TTL_S + 60)
    assert rows and stale  # read back a day later: stale, so it gets refreshed
