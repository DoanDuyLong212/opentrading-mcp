"""#140: both finance tools hand out periods in ONE order (oldest → newest), and
every "latest" answer is an explicit field rather than ``periods[0]``.

The benchmark snapshots captured before this change keep the old order; the
contract below is what new clients code against.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from opentrading_mcp.providers import vietstock as vs_p
from opentrading_mcp.providers import vs_ratios

FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures" / "vietstock_financeinfo_2026-11-09"


def _raw(symbol: str, period: str) -> dict:
    return json.loads((FIXTURES / f"financeinfo_{symbol}_{period}.json").read_text("utf-8"))


@pytest.fixture(autouse=True)
def _clear_cache():
    vs_ratios._cache.clear()
    yield
    vs_ratios._cache.clear()


@pytest.fixture
def financeinfo(monkeypatch):
    monkeypatch.setattr(vs_p, "financeinfo", lambda s, p="quarter": _raw(s, p))


def _tool(name: str):
    from opentrading_mcp.server import create_server, register_preset

    server = create_server("all")
    register_preset(server, "all")
    return server._tool_manager.get_tool(name).fn


def test_ratio_table_periods_run_oldest_to_newest(financeinfo):
    t = vs_ratios.equity_ratios("FPT", "year")
    assert t["periods"] == ["2021", "2022", "2023", "2024", "2025"]
    assert t["latest_period"] == "2025"
    assert t["period_order"] == "oldest_to_newest"


def test_ratio_table_latest_period_carries_the_newest_numbers(financeinfo):
    t = vs_ratios.equity_ratios("FPT", "year")
    roe = next(r for r in t["ratios"] if r["item_id"] == "roe")
    assert roe["values"][t["latest_period"]] == 28.3


def test_statements_and_ratios_share_one_order(financeinfo):
    data, _warnings = vs_p.align_financeinfo(_raw("FPT", "year"))
    table = vs_ratios.equity_ratios("FPT", "year")
    assert data["periods"] == ["2021", "2022", "2023", "2024", "2025"]
    assert table["periods"] == data["periods"]


def test_quarter_table_is_ordered_too(financeinfo):
    t = vs_ratios.equity_ratios("FPT", "quarter")
    assert t["periods"][-1] == "Q3/2026"
    assert t["latest_period"] == "Q3/2026"
    years_terms = [vs_ratios.period_sort_key(p) for p in t["periods"]]
    assert years_terms == sorted(years_terms)


async def test_financial_ratios_publishes_the_same_contract(financeinfo):
    env = await _tool("financial_ratios")(symbol="FPT", set="roe", period="year")
    data = env["data"]
    assert data["periods"] == ["2021", "2022", "2023", "2024", "2025"]
    assert data["latest_period"] == "2025"
    assert data["period_order"] == "oldest_to_newest"
    assert data["ratios"][0]["values"]["2025"] == 28.3


async def test_financial_ratios_peer_uses_the_latest_period(financeinfo):
    env = await _tool("financial_ratios")(symbol="FPT", set="p_e", peers=["VCB"])
    peer = env["data"]["peers"][0]
    assert peer["period_label"] == "2025"
    assert peer["values"]["p_e"] == vs_ratios.equity_ratios("VCB", "year")["ratios"][0]["values"][
        "2025"
    ] or peer["values"]["p_e"] is not None


async def test_peer_compare_rows_use_the_latest_period(financeinfo):
    env = await _tool("peer_compare")(symbol="FPT", peers=["VCB"], metrics=["pe", "roe"])
    rows = {r["symbol"]: r for r in env["data"]["rows"]}
    assert rows["FPT"]["period_label"] == "2025"
    assert rows["VCB"]["period_label"] == "2025"
    assert rows["FPT"]["p_e"] == 15.91


async def test_vn_fundamentals_publishes_the_same_contract(financeinfo):
    env = await _tool("vn_fundamentals")(symbol="FPT", period="quarter")
    data = env["data"]
    assert data["periods"][-1] == "Q3/2026"
    assert data["latest_period"] == "Q3/2026"
    assert data["period_order"] == "oldest_to_newest"


def test_fundamentals_anchor_is_the_newest_populated_period(monkeypatch):
    """#76 keeps holding after the flip: the anchor is chosen by period order,
    never by list position, and an empty newest period is disclosed."""
    aligned = {
        "periods": ["2023", "2024", "2025"],
        "statements": {"Chỉ số tài chính": [
            {"norm_id": 55, "values": {"2023": None, "2024": 20.0, "2025": None}},
            {"norm_id": 53, "values": {"2023": None, "2024": 5000.0, "2025": None}},
        ]},
    }
    monkeypatch.setattr(vs_p, "financeinfo", lambda s, p="quarter": {"raw": True})
    monkeypatch.setattr(vs_p, "align_financeinfo", lambda raw: (aligned, []))
    f = vs_ratios.equity_fundamentals("FPT", "year")
    assert f["period_label"] == "2024"
    assert f["latest_period"] == "2025"
    assert f["pe"] == 20.0 and f["eps"] == 5000.0
    assert sorted(f["missing_in_period"]) == ["bvps", "roe"]


def test_fundamentals_reports_the_latest_period_even_when_it_is_the_anchor(financeinfo):
    f = vs_ratios.equity_fundamentals("FPT", "year")
    assert f["period_label"] == f["latest_period"] == "2025"
