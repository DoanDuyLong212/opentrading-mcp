"""financial_ratios(period="quarter") must not key values to the wrong quarter.

Live 24/10/2026 FPT gross margin came back as {2026-Q2: 37.89, 2026-Q1: 34.88,
2025-Q4: 39.24}; Vietstock KQKD puts those at Q3/2025, Q4/2025 and Q1/2025. The
KBS quarterly header repeats "2025 Quý 4" and its values do not follow it, so
vnstock returns 2026-Q2, 2025-Q4, 2026-Q1, 2025-Q4_1. Fixture: that frame as
returned (tests/fixtures/vnstock_ratio_fpt_20261023.json, "quarter").
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import ProviderBadData
from opentrading_mcp.server import create_server, register_preset
from opentrading_mcp.tools import compute_financial as comp_fin

RATIOS = json.loads(
    (Path(__file__).parent / "fixtures" / "vnstock_ratio_fpt_20261023.json").read_text(
        encoding="utf-8"
    )
)


def _frame(rows: list[dict[str, Any]], rename: dict[str, str] | None = None) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    return frame.rename(columns=rename) if rename else frame


def _fake_vnstock(monkeypatch, frame: pd.DataFrame) -> None:
    class _Equity:
        def ratio(self, period: str = "year") -> pd.DataFrame:
            return frame

    class Fundamental:
        def equity(self, symbol: str) -> _Equity:
            return _Equity()

    monkeypatch.setitem(sys.modules, "vnstock", types.SimpleNamespace(Fundamental=Fundamental))


def _tool(name: str):
    server = create_server("scan")
    register_preset(server, "scan")
    return server._tool_manager.get_tool(name).fn


def test_recorded_kbs_quarter_frame_is_refused(monkeypatch):
    _fake_vnstock(monkeypatch, _frame(RATIOS["quarter"]))
    with pytest.raises(ProviderBadData, match="repeat period 2025-Q4"):
        vn_p.equity_ratios("FPT", "quarter")


def test_out_of_order_periods_without_duplicates_are_refused(monkeypatch):
    # vnstock's sort by the non-unique header ID alone gives this order.
    rows = [{k: v for k, v in r.items() if k != "2025-Q4_1"} for r in RATIOS["quarter"]]
    _fake_vnstock(monkeypatch, _frame(rows))
    with pytest.raises(ProviderBadData, match="out of order"):
        vn_p.equity_ratios("FPT", "quarter")


def test_clean_quarter_frame_still_parses(monkeypatch):
    rename = {"2026-Q2": "2026-Q2", "2025-Q4": "2026-Q1", "2026-Q1": "2025-Q4",
              "2025-Q4_1": "2025-Q3"}
    _fake_vnstock(monkeypatch, _frame(RATIOS["quarter"], rename))
    out = vn_p.equity_ratios("FPT", "quarter")
    assert out["periods"] == ["2026-Q2", "2026-Q1", "2025-Q4", "2025-Q3"]
    margin = next(r for r in out["ratios"] if r["item_id"] == "gross_profit_margin")
    assert margin["values"] == {
        "2026-Q2": 37.89, "2026-Q1": 39.24, "2025-Q4": 34.88, "2025-Q3": 37.89,
    }


def test_oldest_first_columns_are_accepted(monkeypatch):
    rows = [{"item": "ROE", "item_id": "roe", "2023": 1.0, "2024": 2.0, "2025": 3.0}]
    _fake_vnstock(monkeypatch, _frame(rows))
    assert vn_p.equity_ratios("FPT", "year")["periods"] == ["2025", "2024", "2023"]


def test_annual_frame_is_unchanged(monkeypatch):
    _fake_vnstock(monkeypatch, _frame(RATIOS["year"]))
    out = vn_p.equity_ratios("FPT", "year")
    assert out["periods"] == ["2025", "2024", "2023", "2022"]


def test_fundamentals_do_not_fall_back_on_a_mislabelled_frame(monkeypatch):
    _fake_vnstock(monkeypatch, _frame(RATIOS["quarter"]))
    picked: list[Any] = []
    monkeypatch.setattr(vn_p, "_pick_ratio_number", lambda *a: picked.append(a) or 1.0)
    with pytest.raises(ProviderBadData):
        vn_p.equity_fundamentals("FPT", "quarter")
    assert picked == []


async def test_financial_ratios_quarter_is_unavailable(monkeypatch):
    _fake_vnstock(monkeypatch, _frame(RATIOS["quarter"]))

    async def direct_call(tool: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        return fn(*args)

    monkeypatch.setattr(comp_fin, "_call", direct_call)
    env = await _tool("financial_ratios")(symbol="FPT", set="gross", period="quarter")
    assert env["availability"] == "unavailable"
    assert "ratios" not in env["data"]
    assert "financial_detail" in env["warnings"][0]
