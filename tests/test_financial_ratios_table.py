"""financial_ratios / peer_compare return real ratios from the vnstock table.

Live on 2026-10-23 both tools returned Vietstock overview_trading rows (daily
close, volume, foreign value) under "ratios", with no PE, PB or ROE, and the
`period` argument was echoed but never used. Fixture: the live vnstock ratio
frames for FPT (annual and quarterly).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.server import create_server, register_preset
from opentrading_mcp.tools import compute_financial as comp_fin

RATIOS = json.loads(
    (Path(__file__).parent / "fixtures" / "vnstock_ratio_fpt_20261023.json").read_text(
        encoding="utf-8"
    )
)


def _tool(name: str):
    server = create_server("scan")
    register_preset(server, "scan")
    return server._tool_manager.get_tool(name).fn


def _install(monkeypatch, calls: list[tuple[str, str]]) -> None:
    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        assert fn is vn_p.equity_ratios
        symbol, period = args
        calls.append((symbol, period))
        periods, rows = vn_p._long_ratio_table(pd.DataFrame(RATIOS[period]))
        return {"symbol": symbol.upper(), "period": period, "periods": periods, "ratios": rows}

    monkeypatch.setattr(comp_fin, "_call", fake_call)


def test_ratio_table_keeps_clean_periods_newest_first():
    # The recorded quarterly frame is mislabelled upstream (test_ratio_quarter_labels);
    # the annual one, shuffled, checks the newest-first order.
    frame = pd.DataFrame(RATIOS["year"])[["item", "item_id", "2023", "2025", "2022", "2024"]]
    periods, rows = vn_p._long_ratio_table(frame)
    assert periods == ["2025", "2024", "2023", "2022"]
    pe = next(r for r in rows if r["item_id"] == "p_e")
    assert pe["values"]["2025"] == 15.91
    assert vn_p._discarded_ratio_period_labels(pd.DataFrame(RATIOS["quarter"])) == [
        "2025-Q4_1"
    ]
    by_id = {row["item_id"]: row for row in rows}
    assert by_id["trailing_eps"]["basis"] == "trailing_four_quarters"
    assert by_id["roe"]["basis"] == "reported_period_ratio"


async def test_financial_ratios_returns_the_series_for_the_period(monkeypatch):
    calls: list[tuple[str, str]] = []
    _install(monkeypatch, calls)
    env = await _tool("financial_ratios")(symbol="FPT", set="roe", period="year")
    data = env["data"]
    assert calls == [("FPT", "year")]
    assert data["periods"] == ["2025", "2024", "2023", "2022"]
    assert [r["item_id"] for r in data["ratios"]] == ["roe", "roe_trailling"]
    assert data["ratios"][0]["values"]["2025"] == 28.3
    # The fixture documents zeros, but does not prove missing-data semantics.
    assert data["ratios"][1]["values"] == dict.fromkeys(data["periods"], 0.0)
    assert data["ratios"][1]["suspected_placeholder"] is True
    assert "placeholder" not in data["ratios"][1]
    assert "suspected_placeholder" not in data["ratios"][0]


def test_ratio_table_keeps_genuine_all_zero_metrics():
    frame = pd.DataFrame([
        {"item_id": key, "item": key, "2025": 0.0, "2024": 0.0}
        for key in ("roe", "trailing_eps", "debt_to_equity")
    ])
    periods, rows = vn_p._long_ratio_table(frame)
    assert periods == ["2025", "2024"]
    assert all(row["values"] == {"2025": 0.0, "2024": 0.0} for row in rows)
    assert all("suspected_placeholder" not in row for row in rows)
    values, newest = vn_p._long_ratio_values(frame)
    assert newest == "2025"
    assert values == {"roe": 0.0, "trailing_eps": 0.0, "debt_to_equity": 0.0}


def test_ratio_table_zero_variants_and_real_gaps():
    frame = pd.DataFrame(
        [
            {"item_id": "a", "item": "A", "2025": "0", "2024": 1.0},  # "0" parses as 0
            {"item_id": "b", "item": "B", "2025": 0.0, "2024": None},  # zero next to a gap
            {"item_id": "c", "item": "C", "2025": float("inf"), "2024": float("nan")},
            {"item_id": "d", "item": "D", "2025": "n/a", "2024": 1.5},  # unparseable
        ]
    )
    _, rows = vn_p._long_ratio_table(frame)
    by_id = {r["item_id"]: r["values"] for r in rows}
    assert by_id["a"] == {"2025": 0.0, "2024": 1.0}
    assert by_id["b"] == {"2025": 0.0, "2024": None}
    assert by_id["c"] == {"2025": None, "2024": None}  # non-finite is not a value
    assert by_id["d"] == {"2025": None, "2024": 1.5}


async def test_financial_ratios_cache_hit_keeps_zeros(monkeypatch):
    from opentrading_mcp.providers import store

    monkeypatch.setattr(store, "_memory", {})
    calls: list[tuple[str, str]] = []
    _install(monkeypatch, calls)
    fn = _tool("financial_ratios")
    env = await fn(symbol="FPT", set="roe", period="year")
    assert env["data"]["ratios"][1]["suspected_placeholder"] is True
    env2 = await fn(symbol="FPT", set="roe", period="year")
    assert env2["provenance"]["cached"] is True
    assert calls == [("FPT", "year")]  # second call served from cache
    assert env2["data"]["ratios"][1]["suspected_placeholder"] is True  # survives the round-trip


async def test_financial_ratios_peers_carry_the_newest_period(monkeypatch):
    _install(monkeypatch, [])
    env = await _tool("financial_ratios")(symbol="FPT", set="p_e", peers=["HPG"])
    peer = env["data"]["peers"][0]
    assert {key: peer[key] for key in (
        "symbol", "period_label", "values", "valuation_as_of"
    )} == {
        "symbol": "HPG",
        "period_label": "2025",
        "values": {"p_e": 15.91},
        "valuation_as_of": "cuối kỳ 2025 (không phải hiện tại)",
    }
    assert peer["frequency"] == "annual"
    assert peer["discarded_period_labels"] == []


async def test_peer_compare_metric_aliases(monkeypatch):
    _install(monkeypatch, [])
    env = await _tool("peer_compare")(symbol="FPT", peers=["HPG"], metrics=["pe", "eps", "roe"])
    row = env["data"]["rows"][1]
    assert {key: row[key] for key in (
        "symbol", "period_label", "p_e", "trailing_eps", "roe", "valuation_as_of"
    )} == {
        "symbol": "HPG",
        "period_label": "2025",
        "p_e": 15.91,
        "trailing_eps": 6021.21,
        "roe": 28.3,
        "valuation_as_of": "cuối kỳ 2025 (không phải hiện tại)",
    }
    assert row["metric_basis"] == {
        "trailing_eps": "trailing_four_quarters", "roe": "reported_period_ratio"
    }


async def test_peer_compare_warns_on_a_metric_the_table_lacks(monkeypatch):
    _install(monkeypatch, [])
    env = await _tool("peer_compare")(symbol="FPT", peers=[], metrics=["pe", "market_cap"])
    assert env["data"]["rows"][0]["p_e"] == 15.91
    assert "metric 'market_cap' is not in the vnstock ratio table" in env["warnings"]


async def test_peer_compare_keeps_zero_values(monkeypatch):
    from opentrading_mcp.providers import store

    monkeypatch.setattr(store, "_memory", {})

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        assert fn is vn_p.equity_ratios
        symbol, period = args
        return {
            "symbol": symbol.upper(),
            "period": period,
            "periods": ["2025"],
            "ratios": [{"item_id": "roe", "item": "ROE", "values": {"2025": 0.0}}],
        }

    monkeypatch.setattr(comp_fin, "_call", fake_call)
    fn = _tool("peer_compare")
    env = await fn(symbol="FPT", peers=["HPG"], metrics=["roe"])
    assert env["data"]["rows"][1]["roe"] == 0.0
    env2 = await fn(symbol="FPT", peers=["HPG"], metrics=["roe"])
    assert env2["provenance"]["cached"] is True
    assert env2["data"]["rows"][1]["roe"] == 0.0  # zero survives the cache round-trip


@pytest.mark.parametrize("tool", ["financial_ratios", "peer_compare"])
async def test_suspected_metric_quality_survives_peer_projection_and_cache(monkeypatch, tool):
    calls: list[tuple[str, str]] = []
    _install(monkeypatch, calls)
    fn = _tool(tool)
    kwargs = {"set": "roe", "period": "year"} if tool == "financial_ratios" else {
        "metrics": ["roe_trailling"]
    }
    cold = await fn(symbol="FPT", peers=["AAA"], **kwargs)
    warm = await fn(symbol="FPT", peers=["AAA"], **kwargs)
    assert calls == [("FPT", "year"), ("AAA", "year")]
    assert warm["provenance"]["cached"] is True
    for env in (cold, warm):
        projected = env["data"]["peers"] if tool == "financial_ratios" else env["data"]["rows"]
        assert len(projected) == (1 if tool == "financial_ratios" else 2)
        for row in projected:
            values = row["values"] if tool == "financial_ratios" else row
            assert values["roe_trailling"] == 0.0
            quality = row["metric_quality"]
            assert list(quality) == ["roe_trailling"]
            assert quality["roe_trailling"]["suspected_placeholder"] is True
            note = quality["roe_trailling"]["quality_note"]
            assert "FPT fixture 2026-10-23" in note and "unverified" in note
