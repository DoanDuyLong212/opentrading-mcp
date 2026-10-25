"""Independent model oracles. Full inputs are synthetic, not upstream availability claims."""

from __future__ import annotations

import copy

import pytest

from opentrading_mcp.forensic_models import calculate_forensic
from opentrading_mcp.providers import forensic as source
from opentrading_mcp.server import create_server, register_preset
from opentrading_mcp.tools import compute_financial as tools
from tests.test_forensic_annual_inputs import raw_annual


def full_bundle():
    # Explicit annual contract, including three fields not mapped from real source.
    values = [
        {"assets": 80},
        {
            "assets": 100,
            "revenue": 120,
            "receivables": 12,
            "gross": 24,
            "net_income": 8,
            "cfo": 10,
            "current_assets": 40,
            "current_liabilities": 20,
            "net_ppe": 40,
            "gross_ppe": 40,
            "long_term_debt": 20,
            "current_portion_long_term_debt": 4,
            "depreciation": 8,
            "selling": 4,
            "admin": 2,
        },
        {
            "assets": 140,
            "revenue": 180,
            "receivables": 27,
            "gross": 54,
            "net_income": 18,
            "cfo": 22,
            "current_assets": 60,
            "current_liabilities": 25,
            "net_ppe": 50,
            "gross_ppe": 50,
            "long_term_debt": 15,
            "current_portion_long_term_debt": 3,
            "depreciation": 10,
            "selling": 6,
            "admin": 3,
            "equity_issued": False,
        },
    ]
    records = [
        {
            "year": year,
            "period_start": f"{year}-01-01",
            "period_end": f"{year}-12-31",
            "company_id": 191,
            "scope": "consolidated",
            "source": "synthetic-explicit-contract",
            "business_type": "general",
            "statements": ["KQKD", "CDKT", "LCTT"],
            "values": value,
            "revision": None,
        }
        for year, value in zip((2023, 2024, 2025), values, strict=True)
    ]
    return {"symbol": "SYNTHETIC", "records": records, "latest_observed_year": 2025}


def test_independent_golden_eight_variable_and_nine_signal_oracles():
    d = calculate_forensic(full_bundle())
    want = {
        "dsri": (27 / 180) / (12 / 120),
        "gmi": (24 / 120) / (54 / 180),
        "aqi": (1 - (60 + 50) / 140) / (1 - (40 + 40) / 100),
        "sgi": 180 / 120,
        "depi": (8 / (8 + 40)) / (10 / (10 + 50)),
        "sgai": (9 / 180) / (6 / 120),
        "tata": (18 - 22) / 140,
        "lvgi": ((15 + 25) / 140) / ((20 + 20) / 100),
    }
    expected = (
        -4.84
        + 0.920 * want["dsri"]
        + 0.528 * want["gmi"]
        + 0.404 * want["aqi"]
        + 0.892 * want["sgi"]
        + 0.115 * want["depi"]
        - 0.172 * want["sgai"]
        + 4.679 * want["tata"]
        - 0.327 * want["lvgi"]
    )
    for key, value in want.items():
        assert d[key] == pytest.approx(round(value, 4))
    assert d["m_score"] == round(expected, 4)
    assert d["f_score"] == "9/9"
    assert d["f_passed"] == d["f_evaluated"] == 9
    assert d["beneish"]["status"] == d["piotroski"]["status"] == "complete"
    assert d["beneish"]["input_sources"]["current.net_ppe"]["period_end"] == "2025-12-31"


def test_beneish_does_not_require_third_balance_but_piotroski_does():
    bundle = full_bundle()
    bundle["records"].pop(0)
    d = calculate_forensic(bundle)
    assert d["m_score"] is not None
    assert d["f_score"] is None and d["f_evaluated"] == 6
    assert "beginning.assets" in d["f_missing"]


@pytest.mark.parametrize("field", ["depreciation", "cfo", "net_ppe", "selling", "revenue"])
def test_missing_input_never_scores_truncated_model(field):
    bundle = full_bundle()
    del bundle["records"][-1]["values"][field]
    d = calculate_forensic(bundle)
    assert d["m_score"] is None
    assert f"current.{field}" in d["m_partial"]
    assert not d["flags"] and d["beneish"]["cutoff"] is None


@pytest.mark.parametrize("period_index", [-2, -1])
def test_depi_never_falls_back_to_gross_ppe_in_one_year(period_index):
    bundle = full_bundle()
    del bundle["records"][period_index]["values"]["net_ppe"]
    d = calculate_forensic(bundle)
    period = "previous" if period_index == -2 else "current"
    assert d["depi"] is None and d["m_score"] is None
    assert f"{period}.net_ppe" in d["beneish"]["component_missing"]["depi"]
    assert d["beneish"]["depi_denominator"] == "net_ppe"
    assert not d["flags"] and d["beneish"]["cutoff"] is None


def test_appendix_a_depi_uses_net_ppe_even_when_gross_ppe_differs():
    bundle = full_bundle()
    expected = calculate_forensic(bundle)["depi"]
    bundle["records"][-2]["values"]["gross_ppe"] = 4_000
    bundle["records"][-1]["values"]["gross_ppe"] = 8_000
    d = calculate_forensic(bundle)
    assert d["depi"] == expected
    assert d["beneish"]["depi_denominator"] == "net_ppe"
    assert "current.gross_ppe" not in d["beneish"]["input_sources"]
    assert "current.net_ppe" in d["beneish"]["input_sources"]


def test_no_gross_from_net_income_and_no_equity_inference():
    bundle = full_bundle()
    values = bundle["records"][-1]["values"]
    del values["gross"]
    del values["equity_issued"]
    values.update({"shares": 100, "share_capital": 100})
    d = calculate_forensic(bundle)
    assert d["gmi"] is None and d["m_score"] is None
    assert d["f_score"] is None and d["f_components"]["no_equity_issuance"]["passed"] is None
    values["cogs"] = 126
    assert calculate_forensic(bundle)["gmi"] == pytest.approx(0.6667)


def test_zero_indices_and_zero_income_cfo_are_preserved():
    bundle = full_bundle()
    previous, current = [r["values"] for r in bundle["records"][-2:]]
    previous["gross"] = 0
    current.update({"receivables": 0, "selling": 0, "admin": 0, "net_income": 0, "cfo": 0})
    d = calculate_forensic(bundle)
    assert d["dsri"] == d["gmi"] == d["sgai"] == d["tata"] == 0
    assert d["m_score"] is not None
    assert d["f_components"]["positive_roa"]["passed"] is False
    assert d["f_components"]["positive_cfo"]["passed"] is False
    assert d["f_components"]["no_equity_issuance"]["passed"] is True


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), True])
def test_invalid_assets_do_not_create_scores(value):
    bundle = full_bundle()
    bundle["records"][-1]["values"]["assets"] = value
    d = calculate_forensic(bundle)
    assert d["m_score"] is None
    assert d["f_score"] is None


@pytest.mark.parametrize("business", ["bank", "securities", "insurance", "unknown"])
def test_industry_status_never_defaults_to_general(business):
    bundle = full_bundle()
    for r in bundle["records"]:
        r["business_type"] = business
    d = calculate_forensic(bundle)
    assert d["m_score"] is None and d["f_score"] is None
    assert d["beneish"]["status"] == ("partial" if business == "unknown" else "not_applicable")
    assert d["piotroski"]["status"] == ("partial" if business == "unknown" else "unsupported")


async def test_tool_actual_annual_parser_partial_display_and_versioned_cache(monkeypatch):
    calls, stored, fetched = [], {"v6|FPT|True|1": {"data": {"m_score": 123}}}, []

    def fake_financeinfo(symbol, *, period):
        fetched.append((symbol, period))
        return raw_annual()

    async def fake_call(tool, fn, *args, **kwargs):
        return fn(*args)

    async def lookup(tool, fp):
        calls.append(fp)
        return copy.deepcopy(stored.get(fp))

    async def store(tool, fp, ttl, data, **kwargs):
        from opentrading_mcp.schemas import make_envelope

        env = make_envelope(data, **kwargs)
        stored[fp] = copy.deepcopy(env)
        return env

    monkeypatch.setattr(source.vietstock, "financeinfo", fake_financeinfo)
    monkeypatch.setattr(
        source.vietstock, "annual_forensic_lines",
        lambda symbol, *, years: {"symbol": symbol, "unit_request": 1, "rows": []},
    )
    monkeypatch.setattr(tools, "_call", fake_call)
    monkeypatch.setattr(tools, "cache_lookup", lookup)
    monkeypatch.setattr(tools, "cache_store", store)
    server = create_server("scan")
    register_preset(server, "scan")
    fn = server._tool_manager.get_tool("stock_forensic").fn
    env = await fn("fpt", detail=True, periods_n=1)
    assert env["availability"] == "partial"
    assert env["data"]["m_score"] is None and env["data"]["f_score"] is None
    assert len(env["data"]["annual_inputs"]) == 1
    assert len(env["data"]["beneish"]["periods_used"]) == 2
    assert len(env["data"]["piotroski"]["periods_used"]) == 3
    assert env["data"]["data_time"] == "2025-12-31"
    assert env == await fn("FPT", detail=True, periods_n=1)
    assert fetched == [("FPT", "year")]
    assert calls == ["v7|FPT|True|1"] * 2
    assert "current.depreciation" in env["data"]["m_partial"]
    assert "current.equity_issued" in env["data"]["f_missing"]


@pytest.mark.parametrize("symbol", ["FPT", "VCB"])
async def test_recorded_annual_payload_parser_to_tool(symbol, monkeypatch):
    """Captured public annual sources preserve partial score after safe enrichment."""
    import json
    from pathlib import Path

    raw = json.loads(
        (
            Path(__file__).parent
            / "fixtures"
            / f"financeinfo_{symbol.lower()}_annual_20261024.json"
        ).read_text()
    )
    detail = (
        json.loads(
            (Path(__file__).parent / "fixtures" / "vietstock_fpt_bctc_annual_20261024.json")
            .read_text()
        )
        if symbol == "FPT"
        else {"symbol": symbol, "unit_request": 1, "rows": []}
    )

    def financeinfo(sym, *, period):
        assert sym == symbol and period == "year"
        return copy.deepcopy(raw)

    async def call(tool, fn, *args, **kwargs):
        return fn(*args)

    async def lookup(tool, fp):
        return None

    async def store(tool, fp, ttl, data, **kwargs):
        from opentrading_mcp.schemas import make_envelope

        return make_envelope(data, **kwargs)

    monkeypatch.setattr(source.vietstock, "financeinfo", financeinfo)
    monkeypatch.setattr(
        source.vietstock, "annual_forensic_lines",
        lambda sym, *, years: copy.deepcopy(detail),
    )
    monkeypatch.setattr(tools, "_call", call)
    monkeypatch.setattr(tools, "cache_lookup", lookup)
    monkeypatch.setattr(tools, "cache_store", store)
    server = create_server("scan")
    register_preset(server, "scan")
    env = await server._tool_manager.get_tool("stock_forensic").fn(symbol, detail=True)
    d = env["data"]
    assert env["availability"] == "partial"
    assert d["f_score"] is None  # equity issuance stays unsourced on live data
    assert d["diagnostics"]
    if symbol == "FPT":
        # 3022 and 2242 are observed source lines, not verified equivalents of
        # the canonical Beneish receivables and depreciation definitions.
        assert d["m_score"] is None
        assert d["beneish"]["depi_denominator"] == "net_ppe"
        assert d["data_time"] == "2025-12-31"
        assert d["beneish"]["status"] == "partial"
        assert d["piotroski"]["status"] == "partial"
        assert d["gmi"] is not None and d["sgi"] is not None
        assert d["f_evaluated"] == 7
        assert {"current.receivables", "current.depreciation"} <= set(d["m_partial"])
        assert not d["flags"] and d["beneish"]["cutoff"] is None
        assert "current.cfo" not in d["f_missing"]
        assert d["piotroski"]["input_sources"]["current.cfo"]["source"] == source.BCTC_SOURCE
        assert d["piotroski"]["input_sources"]["current.cfo"]["unit"].startswith("VND")
        assert len(source.normalize_annual(raw)["records"]) == 5
        wider = await server._tool_manager.get_tool("stock_forensic").fn(
            symbol, detail=True, periods_n=5
        )
        assert len(wider["data"]["annual_inputs"]) == 5
        assert len(wider["data"]["beneish"]["periods_used"]) == 2
        assert wider["data"]["f_evaluated"] == d["f_evaluated"]
    else:
        assert d["business_type"] == "bank"
        assert d["beneish"]["status"] == "not_applicable"
        assert d["piotroski"]["status"] == "unsupported"
        assert d["data_time"] is None
        assert d["beneish"]["periods_used"] == {}
        assert d["rejected"] and d["window_missing"]


@pytest.mark.parametrize("field", ["current_portion_long_term_debt", "equity_issued"])
def test_unverified_source_field_missing_does_not_disable_other_components(field):
    bundle = full_bundle()
    del bundle["records"][-1]["values"][field]
    d = calculate_forensic(bundle)
    assert d["m_score"] is not None
    assert d["f_score"] is None and d["f_evaluated"] == 8
    assert f"current.{field}" in d["f_missing"]


@pytest.mark.parametrize("change", ["aqi", "lvgi", "depi"])
def test_corrected_inputs_independently_change_beneish_indices(change):
    bundle = full_bundle()
    before = calculate_forensic(bundle)
    values = bundle["records"][-1]["values"]
    values[{"aqi": "net_ppe", "lvgi": "long_term_debt", "depi": "depreciation"}[change]] += 5
    after = calculate_forensic(bundle)
    assert before[change] != after[change]
    for other in {"aqi", "lvgi", "depi"} - {change}:
        # PPE also determines the depreciation denominator.
        if change == "aqi" and other == "depi":
            continue
        assert before[other] == after[other]


def test_negative_prior_gross_domain_does_not_generate_model_score():
    bundle = full_bundle()
    bundle["records"][-2]["values"]["gross"] = -1
    d = calculate_forensic(bundle)
    assert d["m_score"] is None and d["gmi"] is None
    assert "invalid.previous.gross_margin.negative" in d["m_partial"]


def test_equity_issuance_requires_boolean_not_zero_or_share_count():
    bundle = full_bundle()
    bundle["records"][-1]["values"]["equity_issued"] = 0
    d = calculate_forensic(bundle)
    assert d["f_score"] is None
    assert "current.equity_issued" in d["f_missing"]


def test_conflicting_industry_diagnostics_do_not_infer_financial_type():
    bundle = full_bundle()
    bundle["latest_observed_year"] = 2026
    bundle["diagnostics"] = [{"header": {"BusinessType": 3}}]
    d = calculate_forensic(bundle)
    assert d["business_type"] == "unknown"
    assert d["beneish"]["status"] == "partial" and d["m_score"] is None


@pytest.mark.parametrize(
    ("previous_gross", "current_gross"),
    [(-12, -9), (-12, 54), (0, 54), (-12, 0)],
)
def test_piotroski_signed_gross_margin_improvements(previous_gross, current_gross):
    bundle = full_bundle()
    bundle["records"][-2]["values"]["gross"] = previous_gross
    bundle["records"][-1]["values"]["gross"] = current_gross
    d = calculate_forensic(bundle)
    component = d["f_components"]["gross_margin_increased"]
    assert component == {"passed": True, "missing_inputs": []}
    assert d["f_evaluated"] == 9 and d["f_score"] == "9/9"
    if previous_gross < 0:
        assert d["m_score"] is None
        assert "invalid.previous.gross_margin.negative" in d["m_partial"]
    elif current_gross > 0:
        assert d["gmi"] == 0 and d["m_score"] is not None


def test_piotroski_negative_margin_deterioration_is_evaluated_failure():
    bundle = full_bundle()
    bundle["records"][-2]["values"]["gross"] = -12
    bundle["records"][-1]["values"]["gross"] = -36
    d = calculate_forensic(bundle)
    assert d["f_components"]["gross_margin_increased"] == {"passed": False, "missing_inputs": []}
    assert d["f_evaluated"] == 9 and d["f_score"] == "8/9"
