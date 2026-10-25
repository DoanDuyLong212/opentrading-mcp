"""Contract registry must preserve gaps in source, meaning and publication time."""

from opentrading_mcp.financial_contracts import (
    coverage_for_tool,
    financial_contract_reference,
    forensic_coverage,
    forensic_field_contract,
    forensic_score_contract,
    ratio_field_contract,
    screener_field_contract,
    valuation_field_contract,
)


def _annual_record():
    return {
        "source": "vietstock.financeinfo", "business_type": "general",
        "period_start": "2025-01-01", "period_end": "2025-12-31",
        "scope": "consolidated", "revision": None, "unit": "VND",
        "values": {
            "revenue": 0.0, "cfo": -20.0, "trade_receivables_observed": 15.0,
            "depreciation_and_investment_property_observed": 7.0, "assets": None,
        },
        "input_provenance": {
            "cfo": {"source": "vietstock.BCTC_LoadReportData_Async", "norm_id": 2234,
                    "published_on": "2026-03-01", "revision_status": "not_reported"},
            "trade_receivables_observed": {
                "source": "vietstock.BCTC_LoadReportData_Async",
                "norm_id": 3022, "published_on": "2026-03-01",
            },
            "depreciation_and_investment_property_observed": {
                "source": "vietstock.BCTC_LoadReportData_Async",
                "norm_id": 2242, "published_on": "2026-03-01",
            },
        },
    }


def test_zero_is_supported_missing_is_partial_and_unknown_not_zero():
    row = _annual_record()
    assert forensic_field_contract(row, "revenue")["status"] == "supported"
    assert forensic_field_contract(row, "assets")["status"] == "partial"
    missing = forensic_field_contract(row, "current_portion_long_term_debt")
    assert missing["status"] == "unknown"
    assert missing["source"] is None
    assert missing["norm_id"] is None
    assert forensic_field_contract(row, "equity_issued")["status"] == "unknown"
    assert forensic_field_contract(row, "unrecognized_norm")["status"] == "unknown"


def test_publication_known_only_for_matching_enriched_field():
    row = _annual_record()
    cfo = forensic_field_contract(row, "cfo")
    assert cfo["status"] == "supported"
    assert cfo["source"] == "vietstock.BCTC_LoadReportData_Async"
    assert cfo["publication_as_of"] == "2026-03-01"
    assert cfo["scope"] == "consolidated"
    assert cfo["revision"] is None
    assert forensic_field_contract(row, "revenue")["publication_as_of"] is None


def test_inherited_financeinfo_cfo_id_is_candidate_until_live_proven():
    row = _annual_record()
    row["input_provenance"].pop("cfo")
    cfo = forensic_field_contract(row, "cfo")
    assert cfo["status"] == "unknown"
    assert cfo["source"] is None
    assert cfo["norm_id"] is None
    assert cfo["candidate_norm_id"] == 2234


def test_financeinfo_net_ppe_needs_both_exact_components():
    row = _annual_record()
    row["values"].update({"net_tangible_ppe": 10.0, "net_leased_ppe": 0.0, "net_ppe": 10.0})
    net = forensic_field_contract(row, "net_ppe")
    assert net["status"] == "supported"
    assert net["source"] == "vietstock.financeinfo"
    assert net["components"] == [3035, 3036]
    assert net["publication_as_of"] is None
    row["values"].pop("net_leased_ppe")
    assert forensic_field_contract(row, "net_ppe")["status"] == "unknown"
    row["values"]["net_leased_ppe"] = 2.0
    assert forensic_field_contract(row, "net_ppe")["status"] == "unknown"


def test_present_unproven_beneish_semantics_remain_unknown():
    row = _annual_record()
    for field in ("receivables", "depreciation"):
        contract = forensic_field_contract(row, field)
        assert contract["status"] == "unknown"
        assert contract["norm_id"] is None
        assert contract["semantic_limitation"]
    for field, norm in (("trade_receivables_observed", 3022),
                        ("depreciation_and_investment_property_observed", 2242)):
        contract = forensic_field_contract(row, field)
        assert contract["status"] == "supported"
        assert contract["norm_id"] == norm
        assert contract["semantic_limitation"]
    assert "current_portion_long_term_debt" in forensic_coverage(row)


def test_financial_industry_not_applicable_does_not_infer_zero():
    row = _annual_record()
    row["business_type"] = "bank"
    assert forensic_field_contract(row, "revenue")["status"] == "not_applicable"
    assert forensic_field_contract(row, "equity_issued")["status"] == "not_applicable"


def test_ratio_screener_and_valuation_do_not_fabricate_missing_metadata():
    ratio = ratio_field_contract("p_e", 0.0, period="2025", frequency="annual")
    assert ratio["status"] == "supported"
    assert ratio["period_basis"] == "period_end_price"
    assert ratio["publication_as_of"] is None
    assert ratio_field_contract("provider_new_item", 12.0)["status"] == "unknown"
    suspect = ratio_field_contract(
        "roe_trailling", 0.0,
        quality={"suspected_placeholder": True, "quality_note": "all-zero source row"},
    )
    assert suspect["status"] == "partial"
    assert suspect["value_present"] is True
    assert suspect["quality_status"] == "suspected"
    assert suspect["quality_note"] == "all-zero source row"
    assert screener_field_contract("market_cap", 1e12)["status"] == "unknown"
    assert screener_field_contract("roe", float("nan"))["status"] == "partial"
    out = {"price": 20.0, "price_source": "vnstock.equity_quote_batch",
           "price_as_of": None, "price_unit": "unverified", "eps": 0.0}
    price = valuation_field_contract("price", out)
    assert price["status"] == "supported"
    assert price["observation_as_of"] is None
    assert price["unit"] == "unverified"
    assert valuation_field_contract("eps", out)["status"] == "supported"
    assert valuation_field_contract("per", out)["status"] == "partial"


def test_score_status_tracks_model_completeness_and_industry():
    partial = {"m_score": None, "beneish": {"status": "partial", "scope": "consolidated"}}
    assert forensic_score_contract("m_score", partial)["status"] == "partial"
    complete = {"m_score": -2.0, "beneish": {"status": "complete"}}
    assert forensic_score_contract("m_score", complete)["status"] == "supported"
    industry = {"m_score": None, "beneish": {"status": "not_applicable"}}
    assert forensic_score_contract("m_score", industry)["status"] == "not_applicable"
    unsupported = {"f_score": None, "piotroski": {"status": "unsupported"}}
    assert forensic_score_contract("f_score", unsupported)["status"] == "unsupported"


def test_central_coverage_for_all_five_financial_tool_families():
    forensic = coverage_for_tool("stock_forensic", {
        "annual_inputs": [_annual_record()], "m_score": None,
        "beneish": {"status": "partial"}, "piotroski": {"status": "partial"},
    })
    assert forensic["inputs"]["revenue"]["status"] == "supported"
    assert forensic["inputs"]["receivables"]["status"] == "unknown"
    assert forensic["inputs_status"] == "unknown"
    assert forensic["scores"]["m_score"]["status"] == "partial"
    undisclosed = coverage_for_tool("stock_forensic", {"m_score": -1.5,
        "beneish": {"status": "complete"}})
    assert undisclosed["inputs_status"] == "unknown"
    assert undisclosed["inputs_status_reason"] == "requires_detail_true"
    assert undisclosed["scores"]["m_score"]["status"] == "supported"
    bank = _annual_record()
    bank["business_type"] = "bank"
    assert coverage_for_tool("stock_forensic", {"annual_inputs": [bank]})[
        "inputs_status"
    ] == "not_applicable"
    valuation = coverage_for_tool("valuation_run", {"price": 0.0, "price_as_of": None})
    assert valuation["price"]["status"] == "supported"
    assert valuation["eps"]["status"] == "partial"
    ratios = coverage_for_tool("financial_ratios", {
        "periods": ["2025", "2024"], "frequency": "annual",
        "ratios": [{"item_id": "p_e", "values": {"2025": 0, "2024": None}},
                   {"item_id": "new_provider_id", "values": {"2025": 10, "2024": 9}},
                   {"item_id": "roe_trailling", "values": {"2025": 0, "2024": 0},
                    "suspected_placeholder": True, "quality_note": "all-zero source row"}],
        "peers": [{"symbol": "VCB", "period_label": "2025", "frequency": "annual",
                   "values": {"roe_trailling": 0.0},
                   "metric_quality": {"roe_trailling": {
                       "suspected_placeholder": True,
                       "quality_note": "all-zero source row"}}}],
    })
    assert ratios["coverage_scope"] == "all_reported_periods"
    assert ratios["periods"]["2025"]["p_e"]["status"] == "supported"
    assert ratios["periods"]["2024"]["p_e"]["status"] == "partial"
    assert ratios["periods"]["2025"]["new_provider_id"]["status"] == "unknown"
    assert ratios["periods"]["2025"]["roe_trailling"]["status"] == "partial"
    assert ratios["peers"]["VCB"]["fields"]["roe_trailling"]["status"] == "partial"
    peers = coverage_for_tool("peer_compare", {
        "rows": [{"symbol": "FPT", "period_label": "2025", "p_e": 15.0,
                  "roe_trailling": 0.0, "metric_quality": {"roe_trailling": {
                      "suspected_placeholder": True, "quality_note": "all-zero source row"}}}],
    })
    assert peers["FPT"]["p_e"]["period"] == "2025"
    assert peers["FPT"]["roe_trailling"]["status"] == "partial"
    screener = coverage_for_tool("stock_screener", {
        "candidates": [{"symbol": "FPT", "pe": 10.0, "fundamentals_period": "2025"}],
    })
    assert screener["FPT"]["pe"]["status"] == "supported"
    assert screener["FPT"]["market_cap"]["status"] == "unknown"


def test_public_reference_names_unverified_inputs_without_fabricating_ids():
    ref = financial_contract_reference()
    assert ref["schema_version"] == "financial-contract-registry-v1"
    assert "unsupported" in ref["status_values"]
    assert "cfo" not in ref["forensic_source_ids"]["financeinfo"]
    assert ref["forensic_candidate_ids_not_live_verified"]["financeinfo"]["cfo"] == 2234
    assert ref["forensic_source_ids"]["bctc"]["trade_receivables_observed"] == 3022
    for field in ("receivables", "depreciation", "equity_issued",
                  "current_portion_long_term_debt"):
        assert field in ref["forensic_model_inputs_without_verified_mapping"]
        assert field not in ref["forensic_source_ids"]["bctc"]
    assert ref["screener_unsupported"] == ["market_cap"]
