"""vnstock_quant.fa replaces the upstream ratio() table (Task 4, plan 2026-11-08).

The gen-6 Open API has no ``ratio()`` (VNSTOCK_ROUTE_UNSUPPORTED): ratios are
computed locally by ``vnstock_quant.fa`` from the three fhsc statements.

Honesty note: these tests stub ``fa.Dataset.load`` AND ``fa.ratios`` with a
long frame whose shape was captured from REAL fa computes on 2026-11-08
(synthetic statements + prices, Rust core) — they pin the adapter's
translation/scaling/cache contracts WITHOUT burning the 30/day community trial
quota. They cannot catch fa output drift. The Rust core itself is exercised
only by ``test_real_fa_compute_shape`` below (quota-gated, opt-in) and by the
live parity harness (scripts/parity_compare.py, needs fhsc keys).
"""

from __future__ import annotations

import os
import sys
import types

import pandas as pd
import pytest
from vnstock_quant import fa

from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable
from opentrading_mcp.server import create_server, register_preset

NP = "IS_PROFIT_AFTER_TAX_FOR_SHAREHOLDERS_OF_PARENT_COMPANY"
REV = "IS_REVENUE"
ASSET = "BS_TOTAL_ASSETS"
EQ = "BS_EQUITY"
CAP = "BS_CHARTER_CAPITAL"


@pytest.fixture(autouse=True)
def _clear_fa_cache():
    """The 6h in-process fa cache must not leak stubbed tables between tests."""
    vn_p._fa_cache.clear()
    yield
    vn_p._fa_cache.clear()


def _stmt(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(
        rows, columns=["period", "id", "name", "order", "level", "off_balance", "unit", "value"]
    )


def _statements() -> list[pd.DataFrame]:
    quarters = []
    for q in ("2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"):
        quarters += [
            (q, REV, "Doanh thu thuần", 1, 1, False, "VNĐ", 16000e9),
            (q, NP, "LNST cổ đông mẹ", 2, 1, False, "VNĐ", 1500e9),
            (q, ASSET, "Tổng tài sản", 3, 1, False, "VNĐ", 125000e9),
            (q, EQ, "VCSH cổ đông mẹ", 4, 1, False, "VNĐ", 42000e9),
            (q, CAP, "Vốn điều lệ", 5, 1, False, "VNĐ", 38650e9),
        ]
    return [_stmt(quarters)]


def _prices() -> pd.DataFrame:
    return pd.DataFrame({"time": ["2025-12-31", "2025-12-30"], "close": [150000.0, 148000.0]})


def _fa_long() -> pd.DataFrame:
    """A fa.ratios long frame in the REAL shape (columns + RT ids + units),
    captured from live compute probes on 2026-11-08 (FPT synthetic statements,
    prices 150k / 3.865bn shares). Tests stub fa with this so the suite never
    burns the 30/day community trial quota."""
    rows = [
        # (period, id, value, unit, reason)
        ("2025-Q4", "RT_VALUE_PE", 96.625, "times", ""),
        ("2025-Q4", "RT_VALUE_PB", 3.57, "times", ""),
        ("2025-Q4", "RT_VALUE_EPS", 6000e9 / 3.865e9, "VND/share", ""),
        ("2025-Q4", "RT_VALUE_BVPS", 42000e9 / 3.865e9, "VND/share", ""),
        ("2025-Q4", "RT_PRT_ROE", 0.142857, "ratio", ""),
        ("2025-Q4", "RT_PRT_ROA", 0.048, "ratio", ""),
        ("2025-Q4", "RT_PRT_GROSS_MARGIN", float("nan"), "ratio", "MISSING_INPUT:IS_GROSS_PROFIT"),
        ("2025-Q3", "RT_PRT_ROE", 0.142857, "ratio", ""),
        ("2025-Q3", "RT_VALUE_PE", float("nan"), "times", "MISSING_MARKET"),
    ]
    return pd.DataFrame(
        [
            {"symbol": "FPT", "period": p, "id": i, "value": v, "unit": u, "reason": r}
            for p, i, v, u, r in rows
        ]
    )


def _fa_long_year() -> pd.DataFrame:
    """Annual fa rows (audited years), same columns as ``_fa_long``."""
    rows = [
        ("2025", "RT_VALUE_PE", 25.0, "times", ""),
        ("2025", "RT_VALUE_EPS", 6000.0, "VND/share", ""),
        ("2025", "RT_VALUE_BVPS", 21000.0, "VND/share", ""),
        ("2025", "RT_PRT_ROE", 0.28, "ratio", ""),
        ("2024", "RT_VALUE_PE", 20.0, "times", ""),
        ("2024", "RT_VALUE_EPS", 5000.0, "VND/share", ""),
        ("2024", "RT_VALUE_BVPS", 18000.0, "VND/share", ""),
        ("2024", "RT_PRT_ROE", 0.25, "ratio", ""),
    ]
    return pd.DataFrame(
        [
            {"symbol": "FPT", "period": p, "id": i, "value": v, "unit": u, "reason": r}
            for p, i, v, u, r in rows
        ]
    )


def _patch_fa_load(
    monkeypatch,
    *,
    frames: dict[tuple[str, str], pd.DataFrame] | None = None,
) -> list[str]:
    """Stub fa at its own boundary (``Dataset.load`` + ``ratios``) so the real
    ``_fa_to_v4_table`` / ``equity_fundamentals`` code runs.

    ``frames`` maps (symbol, period) to the long frame fa returns; a missing
    key falls back to the FPT fixtures (quarter → ``_fa_long``, year →
    ``_fa_long_year``). The dataset handle carries the symbol so per-symbol
    frames reach the right call.
    """
    calls: list[str] = []
    frames = frames or {}

    def fake_load(symbols, period="both", source=None, estimate_shares=False, **kwargs):
        calls.append(str(source))
        assert source == "fhsc"
        assert estimate_shares is True
        assert period == "both"
        return types.SimpleNamespace(symbol=str(next(iter(symbols))).upper())

    def fake_ratios(
        data, ids=None, period="quarter", profile="vn", overrides=None, format="long", **kwargs
    ):
        assert format == "long"
        assert period in ("quarter", "year")
        key = (data.symbol, period)
        if key in frames:
            return frames[key]
        return _fa_long_year() if period == "year" else _fa_long()

    monkeypatch.setattr(fa.Dataset, "load", staticmethod(fake_load))
    monkeypatch.setattr(fa, "ratios", fake_ratios)
    return calls


def _long(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"symbol": "FPT", "period": p, "id": i, "value": v, "unit": u, "reason": r}
            for p, i, v, u, r in rows
        ],
        columns=["symbol", "period", "id", "value", "unit", "reason"],
    )


# --- equity_ratios: v4 table shape, RT mapping, percent scaling --------------------


def test_equity_ratios_maps_rt_ids_to_v4_table(monkeypatch):
    calls = _patch_fa_load(monkeypatch)
    out = vn_p.equity_ratios("FPT", "quarter")
    assert calls == ["fhsc"]
    assert out["periods"] == ["2025-Q4", "2025-Q3"]
    ids = {r["item_id"] for r in out["ratios"]}
    assert {"trailing_eps", "p_e", "p_b", "roe", "roe_trailling"} <= ids
    roe = next(r for r in out["ratios"] if r["item_id"] == "roe")
    # fa returns decimals (0.142857); the v4 table is percent-scaled
    assert roe["values"]["2025-Q4"] == pytest.approx(14.29, abs=0.01)
    assert roe["values"]["2025-Q3"] == pytest.approx(14.29, abs=0.01)
    pe = next(r for r in out["ratios"] if r["item_id"] == "p_e")
    assert pe["values"]["2025-Q4"] == pytest.approx(96.625)
    assert pe["values"]["2025-Q3"] is None  # MISSING_MARKET cell → None + note
    assert "MISSING_MARKET" in (pe.get("quality_note") or "")
    assert roe.get("rt_id") == "RT_PRT_ROE"


def test_equity_ratios_gross_margin_missing_input_becomes_none(monkeypatch):
    _patch_fa_load(monkeypatch)
    out = vn_p.equity_ratios("FPT", "quarter")
    gm = next(r for r in out["ratios"] if r["item_id"] == "gross_profit_margin")
    assert all(v is None for v in gm["values"].values())
    assert "MISSING_INPUT" in (gm.get("quality_note") or "")


def test_equity_ratios_known_fa_gaps_get_explained_rows(monkeypatch):
    _patch_fa_load(monkeypatch)
    out = vn_p.equity_ratios("FPT", "year")
    dy = next((r for r in out["ratios"] if r["item_id"] == "dividend_yield"), None)
    assert dy is not None and all(v is None for v in dy["values"].values())
    assert set(dy["values"]) == {"2025", "2024"}
    assert "not in vnstock_quant.fa" in (dy.get("quality_note") or "")


def test_equity_ratios_year_period_uses_fa_year(monkeypatch):
    _patch_fa_load(monkeypatch)
    out = vn_p.equity_ratios("FPT", "year")
    assert out["periods"] == ["2025", "2024"]
    assert out["frequency"] == "annual"
    pe = next(r for r in out["ratios"] if r["item_id"] == "p_e")
    assert pe["values"] == {"2025": 25.0, "2024": 20.0}


def test_equity_ratios_raises_bad_data_when_fa_has_no_rows(monkeypatch):
    """#75: v4 never returned empty periods; an empty fa frame must raise
    ProviderBadData (tools turn it into an unavailable envelope), not hand
    callers a table whose periods[0] crashes."""
    _patch_fa_load(monkeypatch, frames={("FPT", "year"): _fa_long_year().iloc[0:0]})
    with pytest.raises(ProviderBadData, match="no usable year period"):
        vn_p.equity_ratios("FPT", "year")


def test_equity_ratios_raises_bad_data_when_every_label_is_discarded(monkeypatch):
    frame = _long([("weird", "RT_PRT_ROE", 0.2, "ratio", "")])
    _patch_fa_load(monkeypatch, frames={("FPT", "year"): frame})
    with pytest.raises(ProviderBadData, match="weird"):
        vn_p.equity_ratios("FPT", "year")


def test_equity_ratios_empty_result_is_not_cached(monkeypatch):
    calls = _patch_fa_load(monkeypatch, frames={("FPT", "year"): _fa_long_year().iloc[0:0]})
    for _ in range(2):
        with pytest.raises(ProviderBadData):
            vn_p.equity_ratios("FPT", "year")
    assert calls == ["fhsc", "fhsc"]


# --- equity_fundamentals: pe/roe fraction + period label ---------------------------


def test_equity_fundamentals_takes_the_newest_period(monkeypatch):
    """Mutant G24 (#94): walking periods oldest-first must fail a test."""
    _patch_fa_load(monkeypatch)
    out = vn_p.equity_fundamentals("FPT", "year")
    assert out["period_label"] == "2025"
    assert out["pe"] == pytest.approx(25.0)
    assert out["eps"] == pytest.approx(6000.0)
    assert out["bvps"] == pytest.approx(21000.0)
    assert out["roe"] == pytest.approx(0.28)


def test_equity_fundamentals_never_mixes_periods(monkeypatch):
    """#76: a 2025 row whose P/E is missing must not borrow the 2024 P/E while
    labelling the result 2025 (the removed v4 guard said: a PE and an EPS never
    mix years)."""
    frame = _long([
        ("2025", "RT_VALUE_PE", float("nan"), "times", "MISSING_MARKET"),
        ("2024", "RT_VALUE_PE", 20.0, "times", ""),
        ("2025", "RT_VALUE_EPS", 6000.0, "VND/share", ""),
        ("2024", "RT_VALUE_EPS", 5000.0, "VND/share", ""),
        ("2025", "RT_PRT_ROE", 0.28, "ratio", ""),
    ])
    _patch_fa_load(monkeypatch, frames={("FPT", "year"): frame})
    out = vn_p.equity_fundamentals("FPT", "year")
    assert out["period_label"] == "2025"
    assert out["pe"] is None  # 2025 P/E is missing; 20.0 belongs to 2024
    assert out["eps"] == pytest.approx(6000.0)
    assert out["roe"] == pytest.approx(0.28)
    assert "pe" in out["missing_in_period"]


def test_equity_fundamentals_skips_a_period_with_no_core_metric(monkeypatch):
    """A newest period holding only non-core rows (e.g. a margin) is not the
    anchor: the label follows the period the returned numbers come from."""
    frame = _long([
        ("2025", "RT_PRT_NET_MARGIN", 0.1, "ratio", ""),
        ("2024", "RT_VALUE_PE", 20.0, "times", ""),
        ("2024", "RT_VALUE_EPS", 5000.0, "VND/share", ""),
    ])
    _patch_fa_load(monkeypatch, frames={("FPT", "year"): frame})
    out = vn_p.equity_fundamentals("FPT", "year")
    assert out["period_label"] == "2024"
    assert out["pe"] == pytest.approx(20.0)
    assert out["eps"] == pytest.approx(5000.0)


def test_equity_fundamentals_eps_basis_follows_the_period(monkeypatch):
    """#76: annual fa rows are the audited year, not TTM."""
    _patch_fa_load(monkeypatch)
    assert vn_p.equity_fundamentals("FPT", "year")["eps_basis"] == "reported_period_ratio"
    vn_p._fa_cache.clear()
    assert vn_p.equity_fundamentals("FPT", "quarter")["eps_basis"] == "trailing_four_quarters"


def test_equity_fundamentals_passes_discarded_labels_through(monkeypatch):
    frame = pd.concat([
        _fa_long_year(),
        _long([("weird", "RT_PRT_ROE", 0.2, "ratio", "")]),
    ])
    _patch_fa_load(monkeypatch, frames={("FPT", "year"): frame})
    out = vn_p.equity_fundamentals("FPT", "year")
    assert out["discarded_period_labels"] == ["weird"]


def test_equity_fundamentals_from_fa_table(monkeypatch):
    _patch_fa_load(monkeypatch)
    out = vn_p.equity_fundamentals("FPT", "quarter")
    assert out["pe"] == pytest.approx(96.625)
    assert out["roe"] == pytest.approx(0.142857, abs=0.0005)  # fraction, like v4
    assert out["eps"] == pytest.approx(6000e9 / 3.865e9, abs=2.0)  # TTM at quarter periods
    assert out["period_label"] == "2025-Q4"
    assert out["frequency"] == "quarterly"
    assert out["eps_basis"] == "trailing_four_quarters"


def test_equity_fundamentals_raises_unavailable_when_fa_missing(monkeypatch):
    # fa resolving to None simulates a broken vnstock_quant install: the guard
    # turns any internal error into ProviderUnavailable.
    monkeypatch.setitem(sys.modules, "vnstock_quant", types.SimpleNamespace(fa=None))
    with pytest.raises(ProviderUnavailable):
        vn_p.equity_fundamentals("FPT", "quarter")


# --- cashflow: gen-6 Fundamental wide format ---------------------------------------


def test_cashflow_parses_v6_wide_format(monkeypatch):
    wide = pd.DataFrame(
        {
            "item": ["Lưu chuyển tiền thuần từ HĐKD", "Lưu chuyển tiền thuần từ ĐT"],
            "2025-Q3": [-1200e9, 300e9],
            "2025-Q4": [-1500e9, 250e9],
        }
    )

    class Equity:
        def cash_flow(self, period=None, format=None, **kwargs):
            assert period == "quarter"
            return wide

    class Fundamental:
        def __init__(self, source=None, **kwargs):
            assert source == "fhsc"

        def equity(self, symbol):
            return Equity()

    monkeypatch.setitem(sys.modules, "vnstock", types.SimpleNamespace(Fundamental=Fundamental))
    out = vn_p.cashflow("FPT", period="quarter")
    assert out["unit"] == "VNDbn"
    assert out["periods"] == ["2025-Q3", "2025-Q4"]
    assert out["rows"][0]["values"] == [-1200.0, -1500.0]
    assert out["rows"][1]["values"] == [300.0, 250.0]


# --- vn_fundamentals tool: fa table passthrough, report_type kept for cache --------


def test_equity_ratios_caches_fa_computes(monkeypatch):
    """30 fa computes/day on the community tier — one symbol/period = one compute."""
    calls = _patch_fa_load(monkeypatch)
    monkeypatch.setattr(vn_p, "_fa_cache", {})
    first = vn_p.equity_ratios("FPT", "quarter")
    second = vn_p.equity_ratios("FPT", "quarter")
    assert calls == ["fhsc"]  # second call served from the in-process cache
    assert first is second


def test_fa_period_unknown_labels_are_disclosed(monkeypatch):
    """A period label that is not YYYY or YYYY-QN must not silently be 'newest'."""
    long = _fa_long()
    long.loc[len(long)] = {
        "symbol": "FPT", "period": "weird-label", "id": "RT_PRT_ROE",
        "value": 9.9, "unit": "ratio", "reason": "",
    }
    out = vn_p._fa_to_v4_table("FPT", "quarter", long)
    assert "weird-label" not in out["periods"]
    assert "weird-label" in out["discarded_period_labels"]
    assert out["periods"][0] == "2025-Q4"


def test_fa_basis_is_reported_period_for_year_table(monkeypatch):
    """fa year rows are audited periods — the trailing basis only fits quarters."""
    _patch_fa_load(monkeypatch)
    long = _fa_long()
    long = long[long["period"] == "2025-Q4"].assign(period="2025")
    out = vn_p._fa_to_v4_table("FPT", "year", long)
    by_id = {r["item_id"]: r for r in out["ratios"]}
    assert by_id["trailing_eps"].get("basis") == "reported_period_ratio"
    assert by_id["roe_trailling"].get("basis") == "reported_period_ratio"
    # quarter tables keep the TTM basis
    out_q = vn_p._fa_to_v4_table("FPT", "quarter", _fa_long())
    by_id_q = {r["item_id"]: r for r in out_q["ratios"]}
    assert by_id_q["trailing_eps"].get("basis") == "trailing_four_quarters"
    assert by_id_q["roe_trailling"].get("basis") == "trailing_four_quarters"


def test_cashflow_provenance_names_fundamental_route(monkeypatch):
    class Equity:
        def cash_flow(self, period=None, format=None, **kwargs):
            return pd.DataFrame({"item": ["x"], "2025-Q4": [1e9]})

    class Fundamental:
        def __init__(self, source=None, **kwargs):
            pass

        def equity(self, symbol):
            return Equity()

    monkeypatch.setitem(sys.modules, "vnstock", types.SimpleNamespace(Fundamental=Fundamental))
    out = vn_p.cashflow("FPT", period="quarter")
    assert out["source"] == "gen6.fundamental.cash_flow"


@pytest.mark.skipif(
    not os.environ.get("VN6_LIVE_FA"),
    reason="burns the 30/day vnstock_quant trial quota — set VN6_LIVE_FA=1 to run",
)
def test_real_fa_compute_shape():
    """Real Rust fa on synthetic statements: pins the long-frame contract the
    stubbed tests encode (columns, period labels, decimal ratio units)."""
    ds = fa.Dataset.from_frames(
        {"FPT": _statements()}, prices={"FPT": _prices()}, estimate_shares=True
    )
    out = fa.ratios(ds, period="quarter", format="long")
    assert list(out.columns) == ["symbol", "period", "id", "value", "unit", "reason"]
    assert set(out["period"].astype(str)) <= {"2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"}
    roe = out[out["id"] == "RT_PRT_ROE"]
    assert set(roe["unit"]) <= {"ratio"}
    computed = roe[roe["value"].notna()]
    assert computed["value"].between(0, 1).all()


def _tool(name: str, preset: str = "all"):
    server = create_server(preset)
    register_preset(server, preset)
    tool = server._tool_manager.get_tool(name)
    assert tool is not None, name
    return tool.fn


def _empty_year_for(symbol: str) -> dict[tuple[str, str], pd.DataFrame]:
    return {(symbol, "year"): _fa_long_year().iloc[0:0]}


async def test_peer_compare_survives_a_peer_with_no_fa_periods(monkeypatch):
    """#75: one peer without annual fa rows used to raise IndexError out of
    the tool; it must become an error row next to the healthy symbol."""
    _patch_fa_load(monkeypatch, frames=_empty_year_for("VCB"))
    out = await _tool("peer_compare")(symbol="FPT", peers=["VCB"])
    rows = {r["symbol"]: r for r in out["data"]["rows"]}
    assert rows["FPT"]["period_label"] == "2025"
    assert rows["FPT"]["p_e"] == pytest.approx(25.0)
    assert "no usable year period" in rows["VCB"]["error"]
    assert out["availability"] == "partial"


async def test_financial_ratios_survives_a_peer_with_no_fa_periods(monkeypatch):
    _patch_fa_load(monkeypatch, frames=_empty_year_for("VCB"))
    out = await _tool("financial_ratios")(symbol="FPT", peers=["VCB"])
    data = out["data"]
    assert data["periods"] == ["2025", "2024"]
    peer = next(p for p in data["peers"] if p["symbol"] == "VCB")
    assert "no usable year period" in peer["error"]


async def test_financial_ratios_main_symbol_without_periods_is_unavailable(monkeypatch):
    _patch_fa_load(monkeypatch, frames=_empty_year_for("FPT"))
    out = await _tool("financial_ratios")(symbol="FPT")
    assert out["availability"] == "unavailable"


async def test_vn_fundamentals_without_periods_is_unavailable(monkeypatch):
    _patch_fa_load(monkeypatch, frames=_empty_year_for("FPT"))
    out = await _tool("vn_fundamentals")(symbol="FPT", period="year")
    assert out["availability"] == "unavailable"


async def test_vn_fundamentals_returns_fa_table(monkeypatch):
    _patch_fa_load(monkeypatch)
    from opentrading_mcp.tools import vn as vn_tools

    monkeypatch.setattr(vn_tools, "TTL_SECONDS", {"financeinfo": 1})
    monkeypatch.setattr("opentrading_mcp.providers.store._memory", {}, raising=False)
    fn = _tool("vn_fundamentals")
    out = await fn(symbol="FPT", period="quarter", report_type="ttm")
    assert "ratios" in (out.get("data") or out), out
    ids = {r["item_id"] for r in (out.get("data") or out)["ratios"]}
    assert "roe" in ids
