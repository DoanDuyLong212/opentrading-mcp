"""#94: tests for the planted bugs the suite used to miss, plus #92 retry rules.

C09 win_rate, C10 RSI range and G19 listing names survived the mutation run of
the 2026-11-08 review. G24 (newest period) and G12 (fa cache TTL) are covered
by the ratio PRs.
"""

from __future__ import annotations

import random
import sys
import types
from datetime import date, timedelta

import pytest

from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable

# --- C09: win_rate against a hand-computed answer -----------------------------------


def _three_trades() -> tuple[list[float], list[str]]:
    """buy_hold gated to Jan, Mar and May: one rising month (win), one falling
    month (loss), one flat month (a zero P/L, which is not a win)."""
    closes: list[float] = []
    dates: list[str] = []
    day = date(2026, 1, 1)
    while day < date(2026, 6, 1):
        month = day.month
        if month == 1:
            price = 10.0 + day.day  # up all month
        elif month == 2:
            price = 41.0  # carry Jan's end (31 Jan = 41)
        elif month == 3:
            price = 41.0 - day.day  # down all month
        else:
            price = 10.0  # Apr flat bridge, May flat trade
        closes.append(price)
        dates.append(day.isoformat())
        day += timedelta(days=1)
    return closes, dates


def test_win_rate_counts_only_profitable_trades():
    from opentrading_mcp.tools.quant_shared import _run_strategy

    closes, dates = _three_trades()
    out = _run_strategy(closes, "buy_hold", 2, 3, 0.0, dates=dates, months=[1, 3, 5])
    assert out["trades"] == 3
    # 1 win (Jan) of 3 trades: `p >= 0` would count the flat May trade (2/3),
    # counting every trade as a win would give 1.0.
    assert out["win_rate"] == pytest.approx(1 / 3, abs=1e-4)


# --- C10: RSI stays in [0, 100] ---------------------------------------------------


@pytest.mark.parametrize("seed", range(25))
def test_rsi_is_bounded_on_random_series(seed):
    from opentrading_mcp.providers import technicals
    from opentrading_mcp.tools.quant_shared import _rsi_series

    rng = random.Random(seed)
    price, closes = 100.0, []
    for _ in range(80):
        price = max(0.5, price * (1 + rng.gauss(0, 0.04)))
        closes.append(round(price, 2))
    candles = [{"t": f"2026-01-{i % 28 + 1:02d}", "o": c, "h": c, "l": c, "c": c, "v": 1}
               for i, c in enumerate(closes)]
    rsi = technicals.compute(candles)["rsi14"]
    assert rsi is not None and 0.0 <= rsi <= 100.0
    assert all(0.0 <= r <= 100.0 for r in _rsi_series(closes) if r is not None)


def test_rsi_extremes():
    from opentrading_mcp.tools.quant_shared import _rsi_series

    up = [float(i) for i in range(1, 40)]
    assert _rsi_series(up)[-1] == 100.0
    assert _rsi_series([5.0] * 40)[-1] == 50.0


# --- G19: the listing's name column -----------------------------------------------


def test_listing_name_comes_from_organ_name(monkeypatch):
    """A gen-6 column rename used to blank every name silently."""
    from opentrading_mcp.providers import vnstock as vn_p

    class Frame:
        def to_dict(self, orient="records"):
            return [{"symbol": "FPT", "organ_name": "Công ty Cổ phần FPT"},
                    {"symbol": "VCB", "name": "Vietcombank"}]

    class Reference:
        def __init__(self, source=None, **kw):
            self.equity = types.SimpleNamespace(list=lambda **kw: Frame())

    monkeypatch.setitem(sys.modules, "vnstock", types.SimpleNamespace(Reference=Reference))
    monkeypatch.setattr(vn_p, "_listing", None)
    rows = {r["symbol"]: r["name"] for r in vn_p.listing_symbols()}
    assert rows == {"FPT": "Công ty Cổ phần FPT", "VCB": "Vietcombank"}


# --- #92: the cycle fetch retries transient failures only -------------------------


@pytest.fixture
def no_sleep(monkeypatch):
    from opentrading_mcp.tools import cycle_stats

    slept: list[float] = []
    monkeypatch.setattr(cycle_stats.time, "sleep", slept.append)
    return slept


def _fail_with(monkeypatch, exc):
    from opentrading_mcp.providers import vnstock as vn_p

    calls: list[str] = []

    def fake(sym, start, end, interval="1D"):
        calls.append(sym)
        raise exc

    monkeypatch.setattr(vn_p, "candles_range", fake)
    return calls


def test_transient_failures_retry_without_a_final_sleep(monkeypatch, no_sleep):
    from opentrading_mcp.tools.cycle_stats import _fetch_range

    calls = _fail_with(monkeypatch, ProviderUnavailable("upstream down"))
    with pytest.raises(ProviderUnavailable, match="upstream down"):
        _fetch_range("FPT", "2026-01-01", "2026-02-01")
    assert len(calls) == 3
    assert no_sleep == [2, 4]  # was 2, 4, 6: 6 s wasted after the last attempt


@pytest.mark.parametrize(
    "exc",
    [ProviderBadData("malformed candle"),
     ProviderUnavailable("no key", reason="not_configured"),
     ProviderUnavailable("slow down", reason="upstream_rate_limited")],
    ids=["bad-data", "not-configured", "rate-limited"],
)
def test_deterministic_failures_are_not_retried(monkeypatch, no_sleep, exc):
    from opentrading_mcp.tools.cycle_stats import _fetch_range

    calls = _fail_with(monkeypatch, exc)
    with pytest.raises(ProviderUnavailable) as info:
        _fetch_range("FPT", "2026-01-01", "2026-02-01")
    assert calls == ["FPT"] and no_sleep == []
    assert info.value.reason == getattr(exc, "reason", None)  # cycle-refresh backs off on it


def test_vn_asset_fetch_uses_the_shared_retry(monkeypatch):
    from opentrading_mcp.tools import asset_cycle, cycle_stats

    monkeypatch.setattr(cycle_stats, "_fetch_range",
                        lambda s, a, b: [{"t": "2026-01-02", "c": 1700.0, "o": 1.0}])
    assert asset_cycle._fetch_vn_asset("VNINDEX", "2026-01-01", "2026-01-31") == [
        {"t": "2026-01-02", "c": 1700.0}]
