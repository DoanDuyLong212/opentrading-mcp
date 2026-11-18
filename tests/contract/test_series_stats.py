"""#149: series_stats — long-series arithmetic done once, server-side.

Models get relative strength, mean/stdev and rank over a window wrong when they
compute it in a shell. Every value here is checked against hand-computed numbers
in this file; the envelope also names the inputs actually used (dates, sessions,
adjustment) so a reader can audit the result.
"""

from __future__ import annotations

import math

import pytest
from mcp.server.fastmcp import FastMCP

from opentrading_mcp.providers.errors import ProviderUnavailable
from opentrading_mcp.tools import quant_stats
from opentrading_mcp.units import UNITS

DATES = [f"2026-01-0{day}" for day in range(1, 6)]


def _candles(closes: list[float], dates: list[str] | None = None) -> list[dict[str, float]]:
    labels = dates or DATES[: len(closes)]
    return [{"t": label, "c": close} for label, close in zip(labels, closes, strict=True)]


# AAA returns +10%, -10%, +10%, +10%; BBB +5% four times; the index is flat.
CLOSES = {
    "AAA": [100.0, 110.0, 99.0, 108.9, 119.79],
    "BBB": [100.0, 105.0, 110.25, 115.7625, 121.550625],
    "VNINDEX": [1000.0, 1000.0, 1000.0, 1000.0, 1000.0],
}
FETCHED: list[str] = []


@pytest.fixture
def provider(monkeypatch):
    def fake_quote_history(symbol: str, days: int = 365, interval: str = "1D"):
        FETCHED.append(f"{symbol}:{days}:{interval}")
        return _candles(CLOSES[symbol.upper()])

    monkeypatch.setattr(quant_stats.vn_p, "quote_history", fake_quote_history)
    FETCHED.clear()
    return fake_quote_history


def _tool():
    server = FastMCP("series-stats-test")
    quant_stats.register_quant_stats_tools(server)
    return server._tool_manager.get_tool("series_stats").fn


async def test_hand_computed_stats(provider):
    env = await _tool()(["aaa", "BBB", "AAA"], window=4)
    rows = {row["symbol"]: row for row in env["data"]["rows"]}

    aaa, bbb = rows["AAA"], rows["BBB"]
    assert aaa["mean_return_pct"] == pytest.approx(5.0)
    assert aaa["stdev_return_pct"] == pytest.approx(8.6603, abs=1e-4)
    assert aaa["total_return_pct"] == pytest.approx(19.79, abs=1e-4)
    assert aaa["vol_ann_pct"] == pytest.approx(8.6603 * math.sqrt(252), abs=1e-3)
    assert bbb["mean_return_pct"] == pytest.approx(5.0)
    assert bbb["stdev_return_pct"] == pytest.approx(0.0, abs=1e-9)
    assert bbb["total_return_pct"] == pytest.approx(21.5506, abs=1e-4)
    # Rank 1 is the strongest total return over the window.
    assert bbb["rank"] == 1
    assert aaa["rank"] == 2
    # Inputs actually used travel with the values.
    assert env["data"]["inputs"] == {
        "window": 4,
        "sessions": 4,
        "first_date": "2026-01-01",
        "last_date": "2026-01-05",
        "adjusted": "vnstock default (not controlled by this tool)",
        "benchmark": None,
        "dates_missing": False,
    }
    assert env["data"].get("as_of") == "2026-01-05"
    assert env["availability"] == "available"
    assert env["provenance"]["source"] == "computed-local"
    # Two unique symbols, fetched once each.
    assert sorted(FETCHED) == ["AAA:5:1D", "BBB:5:1D"]


async def test_relative_strength_is_total_return_minus_benchmark(provider):
    env = await _tool()(["AAA", "BBB"], window=4, benchmark="vnindex")
    rows = {row["symbol"]: row for row in env["data"]["rows"]}
    assert rows["AAA"]["relative_strength_pct"] == pytest.approx(19.79, abs=1e-4)
    assert rows["BBB"]["relative_strength_pct"] == pytest.approx(21.5506, abs=1e-4)
    assert env["data"]["inputs"]["benchmark"] == "VNINDEX"
    assert "VNINDEX:5:1D" in FETCHED


async def test_metrics_filter_keeps_rank(provider):
    env = await _tool()(["AAA", "BBB"], window=4, metrics=["total_return"])
    row = env["data"]["rows"][0]
    assert row["symbol"] == "BBB"
    assert "total_return_pct" in row
    assert "stdev_return_pct" not in row
    assert "mean_return_pct" not in row
    assert row["rank"] == 1


async def test_shorter_history_reports_sessions_and_warns(provider):
    env = await _tool()(["AAA"], window=60)
    row = env["data"]["rows"][0]
    assert row["sessions"] == 4
    assert env["data"]["inputs"]["sessions"] == 4
    assert any("60" in warning for warning in env["warnings"])


async def test_undated_bars_are_dropped_and_flagged(monkeypatch):
    candles = _candles(CLOSES["AAA"])
    candles[2] = {"t": "", "c": 99.0}

    def fake_quote_history(symbol: str, days: int = 365, interval: str = "1D"):
        return candles

    monkeypatch.setattr(quant_stats.vn_p, "quote_history", fake_quote_history)
    env = await _tool()(["AAA"], window=4)
    assert env["data"]["inputs"]["dates_missing"] is True
    assert any("ngày" in warning for warning in env["warnings"])
    assert env["data"]["rows"][0]["sessions"] == 3


async def test_benchmark_unavailable_still_returns_symbols(provider, monkeypatch):
    def only_two(symbol: str, days: int = 365, interval: str = "1D"):
        if symbol.upper() == "VNINDEX":
            raise ProviderUnavailable("index feed down")
        return _candles(CLOSES[symbol.upper()])

    monkeypatch.setattr(quant_stats.vn_p, "quote_history", only_two)
    env = await _tool()(["AAA"], window=4, benchmark="VNINDEX")
    assert env["availability"] == "available"
    assert "relative_strength_pct" not in env["data"]["rows"][0]
    assert any("index feed down" in warning for warning in env["warnings"])


async def test_provider_failure_is_unavailable(monkeypatch):
    def boom(symbol: str, days: int = 365, interval: str = "1D"):
        raise ProviderUnavailable("no candles")

    monkeypatch.setattr(quant_stats.vn_p, "quote_history", boom)
    env = await _tool()(["AAA"], window=4)
    assert env["availability"] == "unavailable"
    assert env["data"]["tool"] == "series_stats"


async def test_empty_symbols_is_a_contract_error(provider):
    env = await _tool()([], window=4)
    assert env["availability"] == "empty"
    assert env["warnings"]


def test_units_are_published_for_the_tool():
    units = UNITS["series_stats"]
    assert units["mean_return_pct, stdev_return_pct"] == "%/phiên"
    assert units["total_return_pct, relative_strength_pct"] == "% cả cửa sổ"
    assert units["vol_ann_pct"].startswith("%/năm")
    assert "hạng" in units["rank"]
