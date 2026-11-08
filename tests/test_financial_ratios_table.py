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


def _table(period: str) -> dict[str, Any]:
    """Provider-shaped ratio table built from the recorded fixture rows."""
    rows = RATIOS[period]
    cols = [c for c in rows[0] if c not in ("item", "item_id")]
    ordered = sorted(cols, key=lambda c: (int(str(c)[:4]), int(str(c)[6:7] or 0)), reverse=True)
    ratios = [
        {
            "item_id": r["item_id"],
            "item": r["item"],
            "values": {c: (float(r[c]) if r[c] is not None else None) for c in ordered},
            **(
                {"basis": "trailing_four_quarters"}
                if r["item_id"] in ("trailing_eps", "roe_trailling")
                else {}
            ),
        }
        for r in rows
    ]
    return {
        "symbol": "FPT",
        "period": period,
        "frequency": "annual" if period == "year" else "quarterly",
        "periods": ordered,
        "ratios": ratios,
        "discarded_period_labels": [],
    }


def _install(monkeypatch, calls: list[tuple[str, str]]) -> None:
    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        assert fn is vn_p.equity_ratios
        symbol, period = args
        calls.append((symbol, period))
        return _table(period)

    monkeypatch.setattr(comp_fin, "_call", fake_call)


def _fa_long(rows: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["symbol", "period", "id", "value", "unit", "reason"])


def test_fa_table_orders_periods_newest_first_and_scales_ratios():
    # fa emits decimals; the v4 table is percent-scaled and newest-first.
    long = _fa_long(
        [
            {
                "symbol": "FPT",
                "period": "2024",
                "id": "RT_PRT_ROE",
                "value": 0.25,
                "unit": "ratio",
                "reason": "",
            },
            {
                "symbol": "FPT",
                "period": "2025",
                "id": "RT_PRT_ROE",
                "value": 0.283,
                "unit": "ratio",
                "reason": "",
            },
            {
                "symbol": "FPT",
                "period": "2025",
                "id": "RT_VALUE_PE",
                "value": 15.91,
                "unit": "times",
                "reason": "",
            },
        ]
    )
    out = vn_p._fa_to_v4_table("FPT", "year", long)
    assert out["periods"] == ["2025", "2024"]
    by_id = {r["item_id"]: r for r in out["ratios"]}
    assert by_id["p_e"]["values"]["2025"] == 15.91  # multiple stays a multiple
    assert by_id["roe"]["values"]["2025"] == pytest.approx(28.3)  # decimal → percent
    assert by_id["roe"]["rt_id"] == "RT_PRT_ROE"
    assert by_id["roe_trailling"]["values"] == by_id["roe"]["values"]
    if "trailing_eps" in by_id:
        assert by_id["trailing_eps"]["basis"] == "trailing_four_quarters"


async def test_financial_ratios_returns_the_series_for_the_period(monkeypatch):
    calls: list[tuple[str, str]] = []
    _install(monkeypatch, calls)
    env = await _tool("financial_ratios")(symbol="FPT", set="roe", period="year")
    data = env["data"]
    assert calls == [("FPT", "year")]
    assert data["periods"] == ["2025", "2024", "2023", "2022"]
    assert [r["item_id"] for r in data["ratios"]] == ["roe", "roe_trailling"]
    assert data["ratios"][0]["values"]["2025"] == 28.3
    # A computed 0 is a value (fa computes it from statements) — never nulled.
    assert data["ratios"][1]["values"] == dict.fromkeys(data["periods"], 0.0)
    assert "suspected_placeholder" not in data["ratios"][1]


def test_fa_table_keeps_genuine_all_zero_metrics():
    long = _fa_long(
        [
            {
                "symbol": "FPT",
                "period": "2025",
                "id": "RT_PRT_ROE",
                "value": 0.0,
                "unit": "ratio",
                "reason": "",
            },
            {
                "symbol": "FPT",
                "period": "2024",
                "id": "RT_PRT_ROE",
                "value": 0.0,
                "unit": "ratio",
                "reason": "",
            },
        ]
    )
    out = vn_p._fa_to_v4_table("FPT", "year", long)
    roe = next(r for r in out["ratios"] if r["item_id"] == "roe")
    assert roe["values"] == {"2025": 0.0, "2024": 0.0}
    assert "suspected_placeholder" not in roe


def test_fa_table_zero_variants_and_real_gaps():
    long = _fa_long(
        [
            {
                "symbol": "FPT",
                "period": "2025",
                "id": "RT_PRT_ROE",
                "value": 0.0,
                "unit": "ratio",
                "reason": "",
            },  # zero stays zero
            {
                "symbol": "FPT",
                "period": "2024",
                "id": "RT_PRT_ROE",
                "value": float("inf"),
                "unit": "ratio",
                "reason": "",
            },
            {
                "symbol": "FPT",
                "period": "2025",
                "id": "RT_VALUE_PE",
                "value": float("nan"),
                "unit": "times",
                "reason": "MISSING_MARKET",
            },
        ]
    )
    out = vn_p._fa_to_v4_table("FPT", "year", long)
    by_id = {r["item_id"]: r["values"] for r in out["ratios"]}
    assert by_id["roe"]["2025"] == 0.0
    assert by_id["roe"]["2024"] is None  # non-finite is not a value
    assert by_id["p_e"]["2025"] is None
    pe = next(r for r in out["ratios"] if r["item_id"] == "p_e")
    assert "MISSING_MARKET" in (pe.get("quality_note") or "")


async def test_financial_ratios_cache_hit_keeps_zeros(monkeypatch):
    from opentrading_mcp.providers import store

    monkeypatch.setattr(store, "_memory", {})
    calls: list[tuple[str, str]] = []
    _install(monkeypatch, calls)
    fn = _tool("financial_ratios")
    env = await fn(symbol="FPT", set="roe", period="year")
    assert env["data"]["ratios"][1]["values"] == dict.fromkeys(env["data"]["periods"], 0.0)
    env2 = await fn(symbol="FPT", set="roe", period="year")
    assert env2["provenance"]["cached"] is True
    assert calls == [("FPT", "year")]  # second call served from cache
    # zeros survive the cache round-trip
    assert env2["data"]["ratios"][1]["values"] == dict.fromkeys(env2["data"]["periods"], 0.0)


async def test_financial_ratios_peers_carry_the_newest_period(monkeypatch):
    _install(monkeypatch, [])
    env = await _tool("financial_ratios")(symbol="FPT", set="p_e", peers=["HPG"])
    peer = env["data"]["peers"][0]
    assert {key: peer[key] for key in ("symbol", "period_label", "values", "valuation_as_of")} == {
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
    assert {
        key: row[key]
        for key in ("symbol", "period_label", "p_e", "trailing_eps", "roe", "valuation_as_of")
    } == {
        "symbol": "HPG",
        "period_label": "2025",
        "p_e": 15.91,
        "trailing_eps": 6021.21,
        "roe": 28.3,
        "valuation_as_of": "cuối kỳ 2025 (không phải hiện tại)",
    }
    assert row["metric_basis"] == {"trailing_eps": "trailing_four_quarters"}


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
async def test_zero_metrics_survive_peer_projection_and_cache(monkeypatch, tool):
    """A computed 0 keeps its value (and its basis) through projection and cache."""
    calls: list[tuple[str, str]] = []
    _install(monkeypatch, calls)
    fn = _tool(tool)
    kwargs = (
        {"set": "roe", "period": "year"}
        if tool == "financial_ratios"
        else {"metrics": ["roe_trailling"]}
    )
    cold = await fn(symbol="FPT", peers=["AAA"], **kwargs)
    warm = await fn(symbol="FPT", peers=["AAA"], **kwargs)
    assert calls == [("FPT", "year"), ("AAA", "year")]
    assert warm["provenance"]["cached"] is True
    for env in (cold, warm):
        projected = env["data"]["peers"] if tool == "financial_ratios" else env["data"]["rows"]
        assert len(projected) == (1 if tool == "financial_ratios" else 2)
        for row in projected:
            values = row["values"] if tool == "financial_ratios" else row
            assert values["roe_trailling"] == 0.0  # never nulled
            assert "suspected_placeholder" not in str(row)
