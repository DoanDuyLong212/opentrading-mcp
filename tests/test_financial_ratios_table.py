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
    periods, rows = vn_p._long_ratio_table(pd.DataFrame(RATIOS["quarter"]))
    assert periods == ["2026-Q2", "2026-Q1", "2025-Q4"]  # '2025-Q4_1' dropped
    pe = next(r for r in rows if r["item_id"] == "p_e")
    assert pe["values"] == {"2026-Q2": 15.53, "2026-Q1": 15.92, "2025-Q4": 20.96}


async def test_financial_ratios_returns_the_series_for_the_period(monkeypatch):
    calls: list[tuple[str, str]] = []
    _install(monkeypatch, calls)
    env = await _tool("financial_ratios")(symbol="FPT", set="roe", period="year")
    data = env["data"]
    assert calls == [("FPT", "year")]
    assert data["periods"] == ["2025", "2024", "2023", "2022"]
    assert [r["item_id"] for r in data["ratios"]] == ["roe", "roe_trailling"]
    assert data["ratios"][0]["values"]["2025"] == 28.3


async def test_financial_ratios_peers_carry_the_newest_period(monkeypatch):
    _install(monkeypatch, [])
    env = await _tool("financial_ratios")(symbol="FPT", set="p_e", peers=["HPG"])
    peer = env["data"]["peers"][0]
    assert peer == {"symbol": "HPG", "period_label": "2025", "values": {"p_e": 15.91}}


async def test_peer_compare_metric_aliases(monkeypatch):
    _install(monkeypatch, [])
    env = await _tool("peer_compare")(symbol="FPT", peers=["HPG"], metrics=["pe", "eps", "roe"])
    row = env["data"]["rows"][1]
    assert row == {
        "symbol": "HPG",
        "period_label": "2025",
        "p_e": 15.91,
        "trailing_eps": 6021.21,
        "roe": 28.3,
    }
