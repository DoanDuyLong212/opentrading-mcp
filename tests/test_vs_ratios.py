"""Ratio tools on Vietstock financeinfo (N2: fhsc/fa discontinued).

Fixtures are the raw financeinfo payloads for FPT and VCB (year and quarter),
captured 2026-11-09 through the JWT session (no login). Tests stub only
``vietstock.financeinfo`` so the real ``align_financeinfo`` → ratio-table →
tool code runs. The guarantees from #102 carry over: a table is never empty
(#75), fundamentals come from one period (#76), and every row says its basis.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from opentrading_mcp.providers import vietstock as vs_p
from opentrading_mcp.providers import vs_ratios
from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "vietstock_financeinfo_2026-11-09"


def _raw(symbol: str, period: str) -> dict:
    return json.loads((FIXTURES / f"financeinfo_{symbol}_{period}.json").read_text("utf-8"))


@pytest.fixture(autouse=True)
def _clear_cache():
    vs_ratios._cache.clear()
    yield
    vs_ratios._cache.clear()


@pytest.fixture
def financeinfo(monkeypatch):
    """Serve the captured payloads; ``failing`` symbols raise like a dead page."""
    calls: list[tuple[str, str]] = []
    failing: dict[str, Exception] = {}

    def fake(symbol, period="quarter"):
        calls.append((symbol, period))
        if symbol in failing:
            raise failing[symbol]
        return _raw(symbol, period)

    monkeypatch.setattr(vs_p, "financeinfo", fake)
    fake.calls = calls
    fake.failing = failing
    return fake


def _row(table: dict, item_id: str) -> dict:
    return next(r for r in table["ratios"] if r["item_id"] == item_id)


# --- provider: ratio table --------------------------------------------------------


def test_fpt_year_table_matches_the_vietstock_page(financeinfo):
    t = vs_ratios.equity_ratios("FPT", "year")
    assert t["periods"] == ["2025", "2024", "2023", "2022", "2021"]  # newest first
    assert t["frequency"] == "annual" and t["source"] == "vietstock.financeinfo"
    assert _row(t, "p_e")["values"]["2025"] == 15.91
    assert _row(t, "trailing_eps")["values"]["2025"] == 6021.0
    assert _row(t, "book_value_per_share_bvps")["values"]["2025"] == 25680.0
    roe = _row(t, "roe")
    assert roe["values"]["2025"] == 28.3 and roe["unit"] == "percent"
    assert roe["basis"] == "reported_period_ratio"
    assert _row(t, "trailing_eps")["basis"] == "trailing_four_quarters"


def test_derived_rows_use_same_period_figures(financeinfo):
    t = vs_ratios.equity_ratios("FPT", "year")
    pb = _row(t, "p_b")
    assert pb["derived"] is True
    assert pb["values"]["2025"] == pytest.approx(15.91 * 6021 / 25680, abs=0.01)
    gm = _row(t, "gross_profit_margin")
    assert gm["derived"] is True
    assert gm["values"]["2025"] == pytest.approx(25888529512413 / 70112825100710 * 100, abs=0.01)


def test_quarter_returns_are_single_quarter_not_ttm(financeinfo):
    """Vietstock quarter ROE is the quarter's own (FPT ~7 %), not trailing:
    labelling it TTM would be the #76 mistake again."""
    t = vs_ratios.equity_ratios("FPT", "quarter")
    assert t["periods"][0] == "Q3/2026" and t["frequency"] == "quarterly"
    roe = _row(t, "roe")
    assert roe["basis"] == "single_quarter" and roe["values"]["Q3/2026"] == 6.58
    assert _row(t, "trailing_eps")["basis"] == "trailing_four_quarters"


def test_bank_table_has_no_margin_rows(financeinfo):
    t = vs_ratios.equity_ratios("VCB", "year")
    ids = {r["item_id"] for r in t["ratios"]}
    assert "net_profit_margin" not in ids and "gross_profit_margin" not in ids
    assert _row(t, "roe")["values"]["2025"] == 16.73


def test_ids_the_source_lacks_are_explained(financeinfo):
    t = vs_ratios.equity_ratios("FPT", "year")
    for item_id in ("p_s", "ev_ebit", "ev_ebitda", "dividend_yield", "roic", "beta"):
        row = _row(t, item_id)
        assert all(v is None for v in row["values"].values())
        assert "not in Vietstock financeinfo" in row["quality_note"]


def test_no_usable_period_raises_bad_data():
    """#75: callers index periods[0]; an empty table must fail in the provider."""
    aligned = {"periods": ["weird"], "statements": {"Chỉ số tài chính": [
        {"norm_id": 55, "values": {"weird": 1.0}}]}}
    with pytest.raises(ProviderBadData, match="weird"):
        vs_ratios.table_from_financeinfo("FPT", "year", aligned)
    with pytest.raises(ProviderBadData, match="no usable year period"):
        vs_ratios.table_from_financeinfo(
            "FPT", "year", {"periods": [], "statements": {"Chỉ số tài chính": [{"norm_id": 55}]}}
        )


def test_page_without_ratio_block_raises_bad_data():
    with pytest.raises(ProviderBadData, match="no ratio block"):
        vs_ratios.table_from_financeinfo("FPT", "year", {"periods": ["2025"], "statements": {}})


def test_cache_returns_copies_and_fetches_once(financeinfo):
    """#81: the cached table must not be shared mutable state."""
    first = vs_ratios.equity_ratios("FPT", "year")
    first["ratios"].clear()
    second = vs_ratios.equity_ratios("FPT", "year")
    assert second["ratios"]  # not poisoned
    assert financeinfo.calls == [("FPT", "year")]


def test_cache_expires_after_the_ttl(financeinfo, monkeypatch):
    """Mutant G12: a cache that never expires would serve stale ratios forever."""
    clock = {"now": 1000.0}
    monkeypatch.setattr(vs_ratios.time, "monotonic", lambda: clock["now"])
    vs_ratios.equity_ratios("FPT", "year")
    clock["now"] += vs_ratios._TTL - 1
    vs_ratios.equity_ratios("FPT", "year")
    assert financeinfo.calls == [("FPT", "year")]  # still fresh
    clock["now"] += 2
    vs_ratios.equity_ratios("FPT", "year")
    assert financeinfo.calls == [("FPT", "year"), ("FPT", "year")]  # refetched


def test_failures_are_not_cached(financeinfo):
    financeinfo.failing["FPT"] = ProviderUnavailable("vietstock timeout")
    for _ in range(2):
        with pytest.raises(ProviderUnavailable):
            vs_ratios.equity_ratios("FPT", "year")
    assert financeinfo.calls == [("FPT", "year"), ("FPT", "year")]


def test_unknown_period_is_refused(financeinfo):
    with pytest.raises(ProviderBadData, match="year\\|quarter"):
        vs_ratios.equity_ratios("FPT", "ttm")
    assert financeinfo.calls == []


# --- provider: fundamentals -------------------------------------------------------


def test_fundamentals_from_one_period(financeinfo):
    f = vs_ratios.equity_fundamentals("FPT", "year")
    assert f["period_label"] == "2025"
    assert (f["pe"], f["eps"], f["bvps"]) == (15.91, 6021.0, 25680.0)
    assert f["roe"] == pytest.approx(0.283)
    assert f["eps_basis"] == "trailing_four_quarters"
    assert f["roe_basis"] == "reported_period_ratio"
    assert f["missing_in_period"] == []


def test_fundamentals_never_borrow_an_older_period(monkeypatch):
    """#76: a P/E missing in the newest year stays None; 2024's P/E is not shown as 2025."""
    aligned = {
        "periods": ["2024", "2025"],
        "statements": {"Chỉ số tài chính": [
            {"norm_id": 55, "values": {"2024": 20.0, "2025": None}},
            {"norm_id": 53, "values": {"2024": 5000.0, "2025": 6000.0}},
        ]},
    }
    monkeypatch.setattr(vs_p, "financeinfo", lambda s, p="quarter": {"raw": True})
    monkeypatch.setattr(vs_p, "align_financeinfo", lambda raw: (aligned, []))
    f = vs_ratios.equity_fundamentals("FPT", "year")
    assert f["period_label"] == "2025"
    assert f["pe"] is None and f["eps"] == 6000.0
    assert "pe" in f["missing_in_period"]


# --- tools ------------------------------------------------------------------------


def _tool(name: str):
    from opentrading_mcp.server import create_server, register_preset

    server = create_server("all")
    register_preset(server, "all")
    return server._tool_manager.get_tool(name).fn


async def test_peer_compare_reads_vietstock(financeinfo):
    env = await _tool("peer_compare")(symbol="FPT", peers=["VCB"], metrics=["pe", "roe"])
    rows = {r["symbol"]: r for r in env["data"]["rows"]}
    assert rows["FPT"]["period_label"] == "2025" and rows["FPT"]["p_e"] == 15.91
    assert rows["VCB"]["roe"] == 16.73
    assert env["provenance"]["source"] == "vietstock"


async def test_peer_compare_survives_a_peer_without_periods(financeinfo):
    """#75 at tool level: one bad peer is an error row, not a crash."""
    financeinfo.failing["VCB"] = ProviderBadData("Vietstock returned no usable year period for VCB")
    env = await _tool("peer_compare")(symbol="FPT", peers=["VCB"])
    rows = {r["symbol"]: r for r in env["data"]["rows"]}
    assert rows["FPT"]["p_e"] == 15.91
    assert "no usable year period" in rows["VCB"]["error"]
    assert env["availability"] == "partial"


async def test_financial_ratios_peer_error_and_basis(financeinfo):
    financeinfo.failing["VCB"] = ProviderBadData("Vietstock returned no usable year period for VCB")
    env = await _tool("financial_ratios")(symbol="FPT", peers=["VCB"])
    data = env["data"]
    assert data["periods"][0] == "2025"
    roe = next(r for r in data["ratios"] if r["item_id"] == "roe")
    assert roe["basis"] == "reported_period_ratio"
    peer = next(p for p in data["peers"] if p["symbol"] == "VCB")
    assert "no usable year period" in peer["error"]


async def test_financial_ratios_main_symbol_failure_is_unavailable(financeinfo):
    financeinfo.failing["FPT"] = ProviderBadData("Vietstock returned no usable year period for FPT")
    env = await _tool("financial_ratios")(symbol="FPT")
    assert env["availability"] == "unavailable"
    assert "no usable year period" in " ".join(env["warnings"])


async def test_vn_fundamentals_returns_the_vietstock_table(financeinfo):
    env = await _tool("vn_fundamentals")(symbol="FPT", period="quarter")
    assert env["data"]["source"] == "vietstock.financeinfo"
    assert env["data"]["periods"][0] == "Q3/2026"


async def test_vn_fundamentals_session_rejected_is_unavailable(financeinfo):
    from opentrading_mcp.providers.errors import ProviderAuthMissing

    financeinfo.failing["FPT"] = ProviderAuthMissing("vietstock session rejected")
    env = await _tool("vn_fundamentals")(symbol="FPT")
    assert env["availability"] == "unavailable"
