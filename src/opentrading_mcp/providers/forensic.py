"""Strict annual inputs, separate from public statement table formatting.

Use the existing financeinfo(year) request and Value{header.ID} source pattern.
The endpoint does not promise revision ordering: reject conflicting duplicates.
"""

from __future__ import annotations

import calendar
import copy
import math
import re
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from opentrading_mcp.providers import vietstock
from opentrading_mcp.providers.errors import (
    ProviderAuthMissing,
    ProviderBadData,
    ProviderUnavailable,
)

SOURCE = "vietstock.financeinfo"
STATEMENTS = {
    "Kết quả kinh doanh": "KQKD",
    "Báo cáo tình hình tài chính": "CDKT",
    "Lưu chuyển tiền tệ gián tiếp": "LCTT",
    "Lưu chuyển tiền tệ trực tiếp": "LCTT",
}
# KQKD/CDKT IDs verified by financial_detail_fpt_vcb_20261023.json, general only.
# CFO 2234 is inherited from compute_financial.py and test_small_data_fixes.py;
# this is not proof of a recorded live annual CFO payload. No invented IDs for
# annual depreciation expense, current LTD portion or equity issuance.
GENERAL_LINES = {
    "KQKD": {
        2216: "revenue",
        2207: "cogs",
        2217: "gross",
        2212: "net_income",
        2227: "selling",
        2224: "admin",
    },
    "CDKT": {
        2996: "assets",
        3000: "current_assets",
        3014: "current_liabilities",
        # 3005 includes seller prepayments and loans. Beneish (2013) uses
        # Compustat Receivables Total [2], whose definition excludes advances
        # on material purchases. Do not silently equate these line items.
        3003: "cash",
        2997: "liabilities",
        2998: "equity",
        3035: "net_tangible_ppe",
        3036: "net_leased_ppe",
        3078: "long_term_debt",
    },
    "LCTT": {2234: "cfo"},
}
BUSINESS_TYPES = {1: "general", 2: "securities", 3: "bank", 5: "insurance"}
BCTC_SOURCE = "vietstock.BCTC_LoadReportData_Async"
BCTC_ANCHORS = {2216: "revenue", 2212: "net_income", 2996: "assets", 2998: "equity"}
BCTC_FIELDS = {
    2224: "admin",
    2227: "selling",
    2234: "cfo",
    # Observed source lines, but their accounting definitions are narrower or
    # broader than the respective Beneish variables. Preserve for inspection;
    # never promote them to canonical model inputs without a verified bridge.
    2242: "depreciation_and_investment_property_observed",
    3022: "trade_receivables_observed",
    3035: "net_tangible_ppe",
    3036: "net_leased_ppe",
    3078: "long_term_debt",
    3083: "gross_tangible_ppe",
    3084: "accum_dep_tangible_ppe",
    3085: "gross_leased_ppe",
    3086: "accum_dep_leased_ppe",
}


def finite_number(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _month(value: Any, *, end: bool = False) -> date:
    text = str(value)
    if not re.fullmatch(r"\d{6}", text):
        raise ValueError("missing or invalid period boundary")
    year, month = int(text[:4]), int(text[4:])
    return date(year, month, calendar.monthrange(year, month)[1] if end else 1)


def _scope(value: Any) -> str | None:
    # Recorded Unit lookup in financeinfo_fpt_quarter.json; no guessed code aliases.
    return {"HN": "consolidated", "ĐL": "standalone"}.get(str(value or "").strip().upper())


def normalize_annual(raw: dict[str, Any], *, as_of: date | None = None) -> dict[str, Any]:
    """Return annual records plus raw diagnostics, without assuming missing identity.

    Unit=1 means raw VND, including blank row Unit in the recorded fixture. Preserve
    precision until rendering. Missing revision is declared rather than fabricated:
    statements under one raw header share its snapshot, conflicting snapshots cannot
    be ordered. No unsupported annual flow is built from quarterly values.
    """
    through = as_of or datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    candidates: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    rejected: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    observed_years: list[int] = []
    for page_no, page in enumerate(raw.get("pages") or [], 1):
        if not isinstance(page, list):
            continue
        headers = next(
            (
                x
                for x in page
                if isinstance(x, list)
                and x
                and all(isinstance(h, dict) and "YearPeriod" in h for h in x)
            ),
            [],
        )
        sections = next((x for x in page if isinstance(x, dict)), {})
        ids = [h.get("ID") for h in headers]
        unique_ids = all(isinstance(i, int) and not isinstance(i, bool) and i > 0 for i in ids)
        unique_ids = unique_ids and len(ids) == len(set(ids))
        for header in headers:
            provenance = {"page": page_no, "header": dict(header), "source": SOURCE}
            diagnostics.append({**provenance, "statements": sections})
            # A malformed newest annual must not allow a silently stale score.
            # Record its plausible year before column/calendar validation, but do
            # not let quarters or explicitly future periods block completed years.
            year_hint, term_hint = header.get("YearPeriod"), header.get("ReportTermID")
            if (
                isinstance(year_hint, int)
                and not isinstance(year_hint, bool)
                and 1 <= year_hint <= through.year
                and term_hint == 1
                and not isinstance(term_hint, bool)
            ):
                try:
                    hint_start = _month(header.get("PeriodBegin"))
                    hint_end = _month(header.get("PeriodEnd"), end=True)
                    coherent_year = hint_end.year == year_hint
                    twelve_months = (
                        hint_end.year - hint_start.year
                    ) * 12 + hint_end.month - hint_start.month == 11
                    known_future = coherent_year and twelve_months and hint_end > through
                except (ValueError, TypeError):
                    known_future = False
                if not known_future:
                    observed_years.append(year_hint)
            try:
                if not unique_ids:
                    raise ValueError("nonunique or invalid header IDs")
                if isinstance(header.get("ReportTermID"), bool) or header.get("ReportTermID") != 1:
                    raise ValueError("not an explicit annual report")
                start = _month(header.get("PeriodBegin"))
                end = _month(header.get("PeriodEnd"), end=True)
                if (end.year - start.year) * 12 + end.month - start.month != 11:
                    raise ValueError("annual report does not span twelve months")
                year = header.get("YearPeriod")
                if not isinstance(year, int) or isinstance(year, bool) or end.year != year:
                    raise ValueError("fiscal year and period end disagree")
                if end > through:
                    raise ValueError("future period end")
                scope = _scope(header.get("United"))
                if scope is None:
                    raise ValueError("unknown report scope")
                company = header.get("CompanyID")
                if (
                    not isinstance(company, (int, str))
                    or isinstance(company, bool)
                    or str(company).strip() == ""
                ):
                    raise ValueError("missing company identity")
            except (ValueError, TypeError) as exc:
                rejected.append({**provenance, "reason": str(exc)})
                continue
            raw_type = header.get("BusinessType")
            business_type = (
                BUSINESS_TYPES.get(raw_type, "unknown")
                if isinstance(raw_type, int) and not isinstance(raw_type, bool)
                else "unknown"
            )
            values: dict[str, Any] = {}
            statements: dict[str, Any] = {}
            conflicts: list[str] = []
            for name, rows in sections.items():
                statement = STATEMENTS.get(name)
                if statement is None or not isinstance(rows, list):
                    continue
                statements.setdefault(statement, []).extend(rows)
                if business_type != "general":
                    continue
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    field = GENERAL_LINES[statement].get(row.get("ReportNormID"))
                    value = row.get(f"Value{header['ID']}")
                    unit = str(row.get("Unit") or "VND").upper()
                    if field is None or not finite_number(value) or unit not in {"VND", "VNĐ"}:
                        continue
                    if field in values and values[field] != value:
                        conflicts.append(field)
                    values[field] = value
            if conflicts:
                rejected.append(
                    {
                        **provenance,
                        "reason": "conflicting statement lines",
                        "fields": sorted(set(conflicts)),
                    }
                )
                continue
            if "net_tangible_ppe" in values and "net_leased_ppe" in values:
                net_ppe = values["net_tangible_ppe"] + values["net_leased_ppe"]
                if finite_number(net_ppe):
                    values["net_ppe"] = net_ppe
            record = {
                "year": year,
                "period_start": start.isoformat(),
                "period_end": end.isoformat(),
                "company_id": company,
                "scope": scope,
                "business_type": business_type,
                "source": SOURCE,
                "revision": None,
                "revision_status": "not_reported",
                "unit": "VND",
                "values": values,
                "statements": sorted(statements),
                "provenance": [provenance],
            }
            key = (company, year, start, end, scope)
            candidates.setdefault(key, []).append(record)
    records: list[dict[str, Any]] = []
    for observations in candidates.values():
        first = observations[0]
        signature = (first["values"], first["statements"], first["business_type"])
        if any(
            (r["values"], r["statements"], r["business_type"]) != signature
            for r in observations[1:]
        ):
            rejected.append(
                {
                    "year": first["year"],
                    "scope": first["scope"],
                    "reason": "conflicting duplicate; revision ordering unavailable",
                }
            )
            continue
        first["provenance"] = [p for r in observations for p in r["provenance"]]
        records.append(first)
    records.sort(key=lambda r: (r["year"], str(r["company_id"])))
    return {
        "symbol": str(raw.get("symbol") or "").upper(),
        "basis": "annual",
        "source": SOURCE,
        "unit": "VND",
        "as_of": through.isoformat(),
        "records": records,
        "latest_observed_year": max(observed_years, default=None),
        "rejected": rejected,
        "diagnostics": diagnostics,
        "limitations": [
            "revision not reported by verified financeinfo header schema",
            "recorded annual FPT/VCB headers verified 2026-10-24; "
            "missing model fields remain unavailable",
            "financeinfo publication date unavailable; BCTC enrichment does not form "
            "a point-in-time historical dataset",
            "Vietnam 3005 current receivables not proven equivalent to "
            "Compustat Receivables Total [2] for Beneish DSR",
        ],
    }


def _bctc_publication(value: Any) -> date | None:
    match = re.fullmatch(r"/Date\((\d+)\)/", str(value or ""))
    if not match:
        return None
    try:
        return datetime.fromtimestamp(
            int(match.group(1)) / 1000, ZoneInfo("Asia/Ho_Chi_Minh")
        ).date()
    except (OverflowError, ValueError, OSError):
        return None


def _component_sum(
    added: dict[str, Any], keys: tuple[str, ...]
) -> tuple[Any, list[str], list[str]]:
    """Derive a canonical total only from a complete set of observed lines."""
    total, used, absent = None, [], []
    for k in keys:
        v = added.get(k)
        if finite_number(v):
            total = (total or 0) + v
            used.append(k)
        else:
            absent.append(k)
    return (total if not absent else None), used, absent


def enrich_annual(bundle: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    """Use source-backed BCTC lines only after exact annual identity checks.

    FPT 2025 audited report pp. 164-170 matches 2216, 2212, 2996, 2998,
    2234, 3035 and 3078 from this endpoint. The endpoint has no fiscal
    boundaries, so all four amounts must match the same annual financeinfo
    column; UnitedName, stock, year, term and publication must also agree.
    Audited status does not supply revision ordering or point-in-time history.
    """
    out = copy.deepcopy(bundle)
    rows = raw.get("rows") if isinstance(raw, dict) else None
    if (
        not isinstance(rows, list)
        or isinstance(raw.get("unit_request"), bool)
        or raw.get("unit_request") != 1
    ):
        out["limitations"].append("annual BCTC raw VND rows unavailable or unit unverified")
        return out
    symbol = out["symbol"]
    through = date.fromisoformat(out["as_of"])
    by_year: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            out["rejected"].append({
                "source": BCTC_SOURCE,
                "reason": "annual BCTC row is not an object",
            })
            continue
        year = row.get("YearPeriod")
        if isinstance(year, int) and not isinstance(year, bool):
            by_year.setdefault(year, []).append(row)
        else:
            out["rejected"].append({"source": BCTC_SOURCE, "reason": "annual BCTC year malformed"})
    for record in out["records"]:
        if record["business_type"] != "general":
            continue
        year = record["year"]
        observed = by_year.get(year, [])
        if not observed:
            continue
        def reject(reason: str, year: int = year) -> None:
            out["rejected"].append({"year": year, "source": BCTC_SOURCE, "reason": reason})
        if record["scope"] != "consolidated" or raw.get("symbol") != symbol:
            reject("annual BCTC symbol or consolidated scope mismatch")
            continue
        if any(
            not isinstance(row.get("StockCode"), str)
            or not isinstance(row.get("ReportTermID"), int)
            or isinstance(row.get("ReportTermID"), bool)
            or not isinstance(row.get("UnitedName"), str)
            or not isinstance(row.get("AuditedStatusDescription"), str)
            or not isinstance(row.get("NgayCongboBC"), str)
            or not isinstance(row.get("ReportNormId"), int)
            or isinstance(row.get("ReportNormId"), bool)
            for row in observed
        ):
            reject("annual BCTC malformed report identity or norm ID")
            continue
        identities = {
            (
                row.get("StockCode"), row.get("ReportTermID"),
                 row.get("UnitedName"), row.get("AuditedStatusDescription"),
                 row.get("NgayCongboBC"))
            for row in observed
        }
        if len(identities) != 1:
            reject("annual BCTC row identity or revision ambiguous")
            continue
        code, term, scope_name, audit, publication = next(iter(identities))
        published = _bctc_publication(publication)
        if (
            code != symbol or isinstance(term, bool) or term != 1 or scope_name != "Hợp nhất"
            or not audit or published is None
            or not date.fromisoformat(record["period_end"]) < published <= through
        ):
            reject("annual BCTC report scope, term or publication invalid")
            continue
        lines: dict[int, Any] = {}
        for row in observed:
            norm = row.get("ReportNormId")
            if norm in lines:
                reject("annual BCTC duplicate line without revision order")
                break
            lines[norm] = row.get("Value")
        else:
            if any(
                not finite_number(lines.get(norm))
                or lines[norm] != record["values"].get(field)
                for norm, field in BCTC_ANCHORS.items()
            ):
                reject("annual BCTC and financeinfo anchor values disagree")
                continue
            added: dict[str, Any] = {}
            for norm, field in BCTC_FIELDS.items():
                value = lines.get(norm)
                if not finite_number(value):
                    continue
                if field in record["values"] and record["values"][field] != value:
                    reject(f"annual BCTC {field} conflicts with financeinfo")
                    added = {}
                    break
                added[field] = value
            if not added:
                continue
            net_total, net_used, net_absent = _component_sum(
                added, ("net_tangible_ppe", "net_leased_ppe")
            )
            if net_total is not None:
                if "net_ppe" in record["values"] and record["values"]["net_ppe"] != net_total:
                    reject("annual BCTC net PPE conflicts with financeinfo")
                    continue
                added["net_ppe"] = net_total
            gross_total, gross_used, gross_absent = _component_sum(
                added, ("gross_tangible_ppe", "gross_leased_ppe")
            )
            accum_total, _, accum_absent = _component_sum(
                added, ("accum_dep_tangible_ppe", "accum_dep_leased_ppe")
            )
            if gross_total is not None and accum_total is not None:
                net_expected = added.get("net_ppe")
                if net_expected is not None and gross_total + accum_total != net_expected:
                    reject("annual BCTC gross/accumulated PPE inconsistent with net PPE")
                    continue
                if net_expected is not None:
                    added["gross_ppe"] = gross_total
            absent_note = sorted(net_absent + gross_absent + accum_absent)
            if absent_note:
                out["limitations"].append(
                    f"annual BCTC PPE component(s) {absent_note} absent for {year}"
                    " — affected canonical total unavailable; observed components retained"
                )
            record["values"].update(added)
            if "cfo" in added:
                record["statements"] = sorted(set(record["statements"]) | {"LCTT"})
            record["input_provenance"] = {
                field: {
                    "source": BCTC_SOURCE,
                    "norm_id": norm,
                    "published_on": published.isoformat(),
                    "audit_status": audit,
                    "anchor_match": list(BCTC_ANCHORS),
                    "revision_status": "not_reported",
                    "unit": "VND (request Unit=1; four exact anchors)",
                }
                for norm, field in BCTC_FIELDS.items() if field in added
            }
            if "net_ppe" in added:
                record["input_provenance"]["net_ppe"] = {
                    "source": BCTC_SOURCE,
                    "components": net_used,
                    "components_absent": net_absent,
                    "published_on": published.isoformat(),
                    "unit": "VND",
                }
            if "gross_ppe" in added:
                record["input_provenance"]["gross_ppe"] = {
                    "source": BCTC_SOURCE,
                    "components": gross_used,
                    "components_absent": gross_absent,
                    "published_on": published.isoformat(),
                    "unit": "VND",
                }
    return out


def annual_inputs(symbol: str, *, as_of: date | None = None) -> dict[str, Any]:
    """Fetch annual source columns regardless of a tool's display periods_n."""
    bundle = normalize_annual(vietstock.financeinfo(symbol.upper(), period="year"), as_of=as_of)
    latest = bundle.get("latest_observed_year")
    if not isinstance(latest, int) or latest <= 1900 or not any(
        r["business_type"] == "general" for r in bundle["records"]
    ):
        return bundle
    try:
        details = vietstock.annual_forensic_lines(symbol.upper(), years=(latest, latest - 1))
    except (ProviderAuthMissing, ProviderBadData, ProviderUnavailable) as exc:
        bundle["limitations"].append(f"annual BCTC detail unavailable: {type(exc).__name__}")
        return bundle
    return enrich_annual(bundle, details)


def derive_quarter_cfo(current: dict[str, Any], previous: dict[str, Any] | None = None) -> Any:
    """Subtract compatible explicit YTD values; never consume unscoped LCTT tables.

    Normalized input must provide company/scope/source/revision/fiscal-year identity,
    term Q1/6T/9T/NAM, fiscal start, period end, basis=ytd and raw numeric value.
    """
    identity = ("company_id", "scope", "source", "revision", "fiscal_year", "period_start")
    if any(current.get(k) is None or current.get(k) == "" for k in identity):
        raise ValueError("CFO YTD identity incomplete")
    if current.get("basis") != "ytd" or not finite_number(current.get("value")):
        raise ValueError("CFO requires finite explicit YTD value")
    ends = {"Q1": 3, "6T": 6, "9T": 9, "NAM": 12}
    term = current.get("term")
    if term not in ends:
        raise ValueError("unsupported YTD term")
    if current["scope"] not in {"consolidated", "standalone", "parent"}:
        raise ValueError("CFO YTD scope unknown")
    start = date.fromisoformat(current["period_start"])
    end = date.fromisoformat(current["period_end"])
    fiscal_end_year = start.year + (start.month > 1)
    if (
        start.day != 1
        or end.day != calendar.monthrange(end.year, end.month)[1]
        or current["fiscal_year"] != fiscal_end_year
    ):
        raise ValueError("invalid fiscal YTD boundaries")
    if (end.year - start.year) * 12 + end.month - start.month + 1 != ends[term]:
        raise ValueError("YTD term and boundaries disagree")
    if term == "Q1":
        return current["value"]
    required = {"6T": "Q1", "9T": "6T", "NAM": "9T"}[term]
    if previous is None or any(previous.get(k) != current[k] for k in identity):
        raise ValueError("CFO YTD identity mismatch")
    if previous.get("term") != required:
        raise ValueError("CFO preceding YTD term missing")
    prior_end = date.fromisoformat(previous["period_end"])
    if (
        (prior_end.year - start.year) * 12 + prior_end.month - start.month + 1 != ends[required]
        or prior_end.day != calendar.monthrange(prior_end.year, prior_end.month)[1]
        or previous.get("basis") != "ytd"
        or not finite_number(previous.get("value"))
    ):
        raise ValueError("invalid preceding YTD observation")
    delta = current["value"] - previous["value"]
    if not finite_number(delta):
        raise ValueError("nonfinite derived CFO")
    return delta


def select_annual_window(bundle: dict[str, Any]) -> dict[str, Any]:
    """Select two flows/three balance dates with one company and fiscal calendar.

    Prefer the newest observed year; do not conceal a missing new report by silently
    scoring an older year. Missing LCTT/individual lines are calculator diagnostics.
    """
    records = bundle.get("records") or []
    result: dict[str, Any] = {
        "current": None,
        "previous": None,
        "beginning": None,
        "missing_inputs": [],
        "report_scope": None,
    }
    if not records:
        result["missing_inputs"] = ["annual_records"]
        return result
    latest = bundle.get("latest_observed_year") or max(r["year"] for r in records)
    current = [r for r in records if r["year"] == latest]
    # Prefer the recorded consolidated scope, never a mixture across years.
    # Different companies or fiscal calendars remain ambiguous.
    companies = {r["company_id"] for r in current}
    if len(companies) == 1 and any(r["scope"] == "consolidated" for r in current):
        current = [r for r in current if r["scope"] == "consolidated"]
    if len(current) != 1:
        result["missing_inputs"] = ["unambiguous_current_report_identity"]
        return result
    now = current[0]
    result["current"] = now
    result["report_scope"] = now["scope"]
    identity = ("company_id", "scope", "source", "business_type")
    end = date.fromisoformat(now["period_end"])
    for back, label in ((0, "current"), (1, "previous"), (2, "beginning")):
        target = latest - back
        matches = [
            r
            for r in records
            if r["year"] == target
            and all(r[k] == now[k] for k in identity)
            and date.fromisoformat(r["period_end"]).month == end.month
        ]
        if len(matches) != 1:
            result["missing_inputs"].append(f"{label}.annual_identity")
            continue
        record = matches[0]
        result[label] = record
        required = ("CDKT", "KQKD") if back < 2 else ("CDKT",)
        result["missing_inputs"].extend(
            f"{label}.{s}" for s in required if s not in record["statements"]
        )
    return result
