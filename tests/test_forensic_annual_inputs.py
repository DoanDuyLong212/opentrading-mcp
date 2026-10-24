"""Synthetic annual header harness, NOT a recorded live annual payload.

Shape/ID mappings follow financeinfo_fpt_quarter.json; norm IDs follow the live
financial_detail fixture. Tests do not assert annual upstream data availability.
"""

from __future__ import annotations

import copy
from datetime import date

import pytest

from opentrading_mcp.providers import forensic as f

AS_OF = date(2026, 10, 24)


def raw_annual():
    headers = [
        {
            "ID": i,
            "CompanyID": 191,
            "YearPeriod": y,
            "ReportTermID": 1,
            "TermCode": "NAM",
            "United": "HN",
            "AuditedStatus": "KT",
            "PeriodBegin": f"{y}01",
            "PeriodEnd": f"{y}12",
            "BusinessType": 1,
        }
        for i, y in [(3, 2023), (1, 2025), (2, 2024)]
    ]

    def row(norm, one, two, three):
        return {
            "ReportNormID": norm,
            "Name": "synthetic",
            "Unit": "",
            "Value1": one,
            "Value2": two,
            "Value3": three,
        }

    return {
        "symbol": "FPT",
        "period": "year",
        "pages": [
            [
                headers,
                {
                    "Kết quả kinh doanh": [
                        row(2216, 9007199254740993, 200, None),
                        row(2212, 0, -4, None),
                    ],
                    "Báo cáo tình hình tài chính": [
                        row(2996, 400, 300, 200),
                        row(3035, 100, 90, 80),
                        row(3036, 0, 0, 0),
                        row(3037, 999, 999, 999),
                    ],
                },
            ]
        ],
    }


def parsed(raw=None):
    return f.normalize_annual(raw or raw_annual(), as_of=AS_OF)


def test_header_id_mapping_precision_zero_and_ppe():
    out = parsed()
    assert [r["year"] for r in out["records"]] == [2023, 2024, 2025]
    now = out["records"][-1]
    assert now["values"]["revenue"] == 9007199254740993
    assert isinstance(now["values"]["revenue"], int)
    assert now["values"]["net_income"] == 0
    assert now["values"]["net_ppe"] == 100  # excludes intangible 999
    assert now["unit"] == "VND"
    assert now["revision"] is None and now["revision_status"] == "not_reported"
    assert now["provenance"][0]["header"]["ID"] == 1
    assert out["diagnostics"] and out["rejected"] == []


def test_unordered_headers_and_rows_do_not_change_values():
    raw = raw_annual()
    raw["pages"][0][0].reverse()
    for rows in raw["pages"][0][1].values():
        rows.reverse()
    assert [r["values"] for r in parsed(raw)["records"]] == [
        r["values"] for r in parsed()["records"]
    ]


@pytest.mark.parametrize(
    ("key", "value", "reason"),
    [
        ("ReportTermID", 5, "annual"),
        ("CompanyID", None, "company"),
        ("United", None, "scope"),
        ("United", "ME", "scope"),
        ("PeriodBegin", "202504", "twelve months"),
        ("PeriodEnd", "202613", "month"),
        ("YearPeriod", 2024, "disagree"),
        ("ID", 2, "header IDs"),
    ],
)
def test_bad_identity_is_rejected_but_diagnostics_retained(key, value, reason):
    raw = raw_annual()
    raw["pages"][0][0][1][key] = value
    out = parsed(raw)
    assert reason in " ".join(r["reason"] for r in out["rejected"])
    assert len(out["diagnostics"]) == 3
    assert all(r["year"] != 2025 for r in out["records"])


def test_future_annual_end_is_rejected():
    out = f.normalize_annual(raw_annual(), as_of=date(2025, 10, 1))
    assert any(r["reason"] == "future period end" for r in out["rejected"])
    assert [r["year"] for r in out["records"]] == [2023, 2024]


@pytest.mark.parametrize(
    "business_type,expected",
    [
        (1, "general"),
        (2, "securities"),
        (3, "bank"),
        (5, "insurance"),
        (None, "unknown"),
        (99, "unknown"),
    ],
)
def test_classification_never_defaults_to_general(business_type, expected):
    raw = raw_annual()
    raw["pages"][0][0][1]["BusinessType"] = business_type
    now = parsed(raw)["records"][-1]
    assert now["business_type"] == expected
    if expected != "general":
        assert now["values"] == {}
    assert now["provenance"][0]["header"]["BusinessType"] == business_type


def test_identical_duplicates_keep_provenance_conflicting_duplicates_cannot_win_by_order():
    raw = raw_annual()
    raw["pages"].append(copy.deepcopy(raw["pages"][0]))
    assert len(parsed(raw)["records"][-1]["provenance"]) == 2
    raw["pages"][1][1]["Kết quả kinh doanh"][0]["Value1"] = 999
    for pages in [raw["pages"], raw["pages"][::-1]]:
        out = parsed({**raw, "pages": pages})
        assert [r["year"] for r in out["records"]] == [2023, 2024]
        assert any("revision ordering unavailable" in r["reason"] for r in out["rejected"])


def test_conflicting_duplicate_lines_do_not_produce_a_record():
    raw = raw_annual()
    rows = raw["pages"][0][1]["Kết quả kinh doanh"]
    rows.append({**rows[0], "Value1": 999})
    assert any(r["reason"] == "conflicting statement lines" for r in parsed(raw)["rejected"])


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), float("-inf"), "0"])
def test_invalid_numeric_values_stay_missing(value):
    raw = raw_annual()
    raw["pages"][0][1]["Kết quả kinh doanh"][0]["Value1"] = value
    assert "revenue" not in parsed(raw)["records"][-1]["values"]


def test_missing_ppe_component_is_not_zero():
    raw = raw_annual()
    raw["pages"][0][1]["Báo cáo tình hình tài chính"][2]["Value1"] = None
    assert "net_ppe" not in parsed(raw)["records"][-1]["values"]


def test_window_needs_three_balances_and_two_flows():
    bundle = parsed()
    bundle["records"][0]["statements"] = ["CDKT"]
    selected = f.select_annual_window(bundle)
    assert selected["missing_inputs"] == []
    assert selected["current"]["year"] == 2025
    assert selected["previous"]["year"] == 2024
    assert selected["beginning"]["year"] == 2023
    bundle["records"].pop(0)
    assert f.select_annual_window(bundle)["missing_inputs"] == ["beginning.annual_identity"]


def test_window_does_not_mix_company_calendar_scope_or_shifted_statement_years():
    for key, value in [
        ("company_id", 999),
        ("scope", "parent"),
        ("period_end", "2024-06-30"),
        ("year", 2022),
    ]:
        bundle = parsed()
        bundle["records"][1][key] = value
        assert "previous.annual_identity" in f.select_annual_window(bundle)["missing_inputs"]
    bundle = parsed()
    bundle["records"][-1]["statements"] = ["CDKT"]
    selected = f.select_annual_window(bundle)
    assert selected["current"]["year"] == 2025
    assert selected["missing_inputs"] == ["current.KQKD"]


def test_provider_uses_supported_year_path_without_output_lookback_limit(monkeypatch):
    calls = []

    def fetch(symbol, period):
        calls.append((symbol, period))
        return raw_annual()

    monkeypatch.setattr(f.vietstock, "financeinfo", fetch)
    bundle = f.annual_inputs("fpt", as_of=AS_OF)
    assert calls == [("FPT", "year")]
    assert len(bundle["records"]) == 3
    assert f.select_annual_window(bundle)["missing_inputs"] == []


def ytd(term, value):
    months = {"Q1": 3, "6T": 6, "9T": 9, "NAM": 12}
    month = months[term]
    import calendar

    return {
        "company_id": 191,
        "scope": "consolidated",
        "source": "verified_fixture",
        "revision": "synthetic_same_revision",
        "fiscal_year": 2025,
        "period_start": "2025-01-01",
        "period_end": f"2025-{month:02}-{calendar.monthrange(2025, month)[1]}",
        "basis": "ytd",
        "term": term,
        "value": value,
    }


@pytest.mark.parametrize(
    ("now", "before", "expected"),
    [
        (ytd("Q1", 0), None, 0),
        (ytd("6T", 30), ytd("Q1", 10), 20),
        (ytd("9T", 25), ytd("6T", 30), -5),
        (ytd("NAM", 45), ytd("9T", 25), 20),
    ],
)
def test_cfo_ytd_derivation(now, before, expected):
    assert f.derive_quarter_cfo(now, before) == expected


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("company_id", 999),
        ("scope", "parent"),
        ("source", "other"),
        ("revision", "other"),
        ("fiscal_year", 2024),
        ("period_start", "2024-01-01"),
        ("term", "6T"),
        ("basis", "quarter"),
        ("period_end", "2025-06-30"),
        ("value", True),
        ("value", float("nan")),
    ],
)
def test_cfo_does_not_subtract_foreign_or_wrong_ytd(field, value):
    previous = {**ytd("Q1", 10), field: value}
    with pytest.raises(ValueError):
        f.derive_quarter_cfo(ytd("6T", 30), previous)


def test_cfo_unknown_revision_and_missing_quarter_are_rejected():
    with pytest.raises(ValueError, match="identity incomplete"):
        f.derive_quarter_cfo({**ytd("Q1", 10), "revision": None})
    with pytest.raises(ValueError, match="identity mismatch"):
        f.derive_quarter_cfo(ytd("6T", 30))


def test_rejected_newest_year_cannot_silently_score_an_older_year():
    raw = raw_annual()
    raw["pages"].append(copy.deepcopy(raw["pages"][0]))
    raw["pages"][1][1]["Kết quả kinh doanh"][0]["Value1"] = 42
    bundle = parsed(raw)
    assert bundle["latest_observed_year"] == 2025
    selected = f.select_annual_window(bundle)
    assert selected["current"] is None
    assert selected["missing_inputs"] == ["unambiguous_current_report_identity"]


def test_recorded_quarterly_payload_is_never_accepted_as_annual():
    import json
    from pathlib import Path

    raw = json.loads(
        (Path(__file__).parent / "fixtures" / "financeinfo_fpt_quarter.json").read_text()
    )
    out = parsed(raw)
    assert out["records"] == []
    assert out["diagnostics"]
    assert all(r["reason"] == "not an explicit annual report" for r in out["rejected"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("scope", "unknown"),
        ("period_start", "2025-01-02"),
        ("period_end", "2025-03-30"),
        ("fiscal_year", 2024),
    ],
)
def test_cfo_fiscal_identity_and_month_end_are_required(field, value):
    with pytest.raises(ValueError):
        f.derive_quarter_cfo({**ytd("Q1", 10), field: value})


def test_fiscal_year_need_not_be_calendar_year():
    raw = raw_annual()
    for header in raw["pages"][0][0]:
        year = header["YearPeriod"]
        header["PeriodBegin"] = f"{year - 1}07"
        header["PeriodEnd"] = f"{year}06"
    assert f.select_annual_window(parsed(raw))["missing_inputs"] == []


def test_cfo_mixed_term_or_cross_year_current_boundary_rejected():
    with pytest.raises(ValueError, match="boundaries disagree"):
        f.derive_quarter_cfo({**ytd("6T", 10), "period_end": "2026-06-30"}, ytd("Q1", 0))


def test_recorded_standalone_code_can_form_a_consistent_window():
    raw = raw_annual()
    for header in raw["pages"][0][0]:
        header["United"] = "ĐL"
    bundle = parsed(raw)
    assert all(r["scope"] == "standalone" for r in bundle["records"])
    selected = f.select_annual_window(bundle)
    assert selected["missing_inputs"] == []
    assert selected["report_scope"] == "standalone"


def test_two_known_scopes_prefer_consolidated_and_never_borrow_parent_year():
    raw = raw_annual()
    other = copy.deepcopy(raw["pages"][0])
    for header in other[0]:
        header["United"] = "ĐL"
    raw["pages"].append(other)
    bundle = parsed(raw)
    assert len(bundle["records"]) == 6
    selected = f.select_annual_window(bundle)
    assert selected["report_scope"] == "consolidated"
    assert selected["missing_inputs"] == []
    bundle["records"] = [
        r for r in bundle["records"] if not (r["year"] == 2024 and r["scope"] == "consolidated")
    ]
    selected = f.select_annual_window(bundle)
    assert selected["previous"] is None
    assert selected["missing_inputs"] == ["previous.annual_identity"]


def test_two_companies_cannot_be_resolved_by_scope_preference():
    raw = raw_annual()
    other = copy.deepcopy(raw["pages"][0])
    for header in other[0]:
        header["CompanyID"] = 999
        header["United"] = "ĐL"
    raw["pages"].append(other)
    selected = f.select_annual_window(parsed(raw))
    assert selected["current"] is None
    assert selected["missing_inputs"] == ["unambiguous_current_report_identity"]


@pytest.mark.parametrize(
    ("field", "value"), [("PeriodBegin", "202504"), ("PeriodEnd", "malformed"), ("ID", 2)]
)
def test_malformed_newest_annual_cannot_use_three_complete_older_years(field, value):
    raw = raw_annual()
    raw["pages"][0][0][1][field] = value
    older = copy.deepcopy(raw_annual()["pages"][0])
    older[0] = [{**older[0][0], "YearPeriod": 2022, "PeriodBegin": "202201", "PeriodEnd": "202212"}]
    raw["pages"].append(older)
    bundle = parsed(raw)
    assert bundle["latest_observed_year"] == 2025
    selected = f.select_annual_window(bundle)
    assert selected["current"] is None
    assert selected["missing_inputs"] == ["unambiguous_current_report_identity"]


def test_finite_guard_and_derived_arithmetic_cannot_overflow():
    assert f.finite_number(10**1000) is False
    with pytest.raises(ValueError, match="nonfinite derived CFO"):
        f.derive_quarter_cfo(ytd("6T", 1e308), ytd("Q1", -1e308))
    raw = raw_annual()
    rows = raw["pages"][0][1]["Báo cáo tình hình tài chính"]
    rows[1]["Value1"] = rows[2]["Value1"] = 1e308
    assert "net_ppe" not in parsed(raw)["records"][-1]["values"]
