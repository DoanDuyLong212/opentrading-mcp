"""Evidence-limited contracts for the financial fields this server currently reads.

This registry describes source and measurement, not the value of an observation.
An absent value, publication date, scope or revision stays ``None``. Unknown
provider item IDs stay unknown even when the provider returned a finite number.
The coverage helpers are pure and do not fetch data or change tool envelopes.
"""

from __future__ import annotations

import math
from typing import Any

from opentrading_mcp.providers.forensic import BCTC_FIELDS, BCTC_SOURCE, GENERAL_LINES, SOURCE

STATUS = frozenset({"supported", "partial", "not_applicable", "unsupported", "unknown"})


def _finite(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


# Source IDs below come from the *implemented* provider maps. The record-level
# input_provenance takes precedence when BCTC enriched a financeinfo column.
_FINANCEINFO_IDS = {
    name: norm for lines in GENERAL_LINES.values() for norm, name in lines.items()
    if name != "cfo"
}
# 2234 was inherited in the financeinfo map but has no recorded live annual
# financeinfo CFO payload. The BCTC 2234 field has independent source evidence.
_FINANCEINFO_CANDIDATES = {"cfo": 2234}
_BCTC_IDS = {name: norm for norm, name in BCTC_FIELDS.items()}
_FORENSIC_INPUTS = frozenset(
    _FINANCEINFO_IDS | _BCTC_IDS | {
        "net_ppe": None, "gross_ppe": None,
        "current_portion_long_term_debt": None, "equity_issued": None,
        "receivables": None, "depreciation": None,
    }
)
_FORENSIC_DERIVED = {
    "net_ppe": "net_tangible_ppe + net_leased_ppe (reported components only)",
    "gross_ppe": "gross_tangible_ppe + gross_leased_ppe (reported components only)",
}
_UNMAPPED = frozenset({"current_portion_long_term_debt", "equity_issued"})
_SEMANTIC_UNPROVEN = {
    "receivables": (
        "Vietstock 3022 trade receivables is not verified as "
        "Beneish Compustat Receivables Total [2]"
    ),
    "depreciation": (
        "Vietstock 2242 may include investment property/goodwill; "
        "Beneish PP&E depreciation equivalence is unverified"
    ),
}
_OBSERVED_LIMITATIONS = {
    "trade_receivables_observed": _SEMANTIC_UNPROVEN["receivables"],
    "depreciation_and_investment_property_observed": _SEMANTIC_UNPROVEN["depreciation"],
}
_PERCENT_RATIOS = frozenset({"roe", "roa", "roe_trailling"})
_VND_PER_SHARE = frozenset({"trailing_eps", "book_value_per_share_bvps"})
_PERIOD_END_MULTIPLES = frozenset({"p_e", "p_b", "p_s", "ev_ebit", "ev_ebitda"})
_FORENSIC_FORMULAS = {
    "m_score": "Beneish eight-variable model, CFO TATA, annual-forensic-v1",
    "f_score": "Piotroski nine binary signals, annual-forensic-v1",
}


def forensic_field_contract(record: dict[str, Any] | None, field: str) -> dict[str, Any]:
    """Describe one annual input, including the actual observation's provenance.

    A missing field is partial only when its source mapping is verified. The two
    unmapped Piotroski inputs remain unknown, never reported as zero or false.
    """
    row = record or {}
    meta = row.get("input_provenance", {}).get(field, {})
    values = row.get("values", {})
    value = values.get(field)
    if field == "net_ppe" and not meta and row.get("source") == SOURCE:
        tangible, leased = values.get("net_tangible_ppe"), values.get("net_leased_ppe")
        if _finite(tangible) and _finite(leased) and _finite(value):
            combined = tangible + leased
            if _finite(combined) and combined == value:
                meta = {
                    "source": SOURCE,
                    "components": [3035, 3036],
                    "revision_status": "not_reported",
                    "unit": row.get("unit", "VND"),
                }
    if field not in _FORENSIC_INPUTS:
        status = "unknown"
    elif row.get("business_type") in {"bank", "securities", "insurance"}:
        status = "not_applicable"
    elif field in _UNMAPPED or field in _SEMANTIC_UNPROVEN:
        status = "unknown"
    elif field == "cfo" and not meta:
        status = "unknown"
    elif field == "equity_issued":
        status = "supported" if isinstance(value, bool) else "partial"
    else:
        status = "supported" if _finite(value) else "partial"
    if field in _FORENSIC_DERIVED and not meta and status == "supported":
        # A synthetic input may be supplied by a caller, but its lineage is not
        # verified by the live provider. Do not imply the component formula ran.
        status = "unknown"
    source = meta.get("source")
    if source is None and field in _FINANCEINFO_IDS and field in values:
        source = row.get("source", SOURCE)
    if source is None and field in _BCTC_IDS and field in values:
        source = BCTC_SOURCE if meta else None
    norm_id = meta.get("norm_id", _FINANCEINFO_IDS.get(field))
    if field in _BCTC_IDS and meta:
        norm_id = meta.get("norm_id", _BCTC_IDS[field])
    return {
        "field": field,
        "status": status,
        "source": source,
        "norm_id": norm_id,
        "components": meta.get("components"),
        "candidate_norm_id": _FINANCEINFO_CANDIDATES.get(field) if not meta else None,
        "formula": _FORENSIC_DERIVED.get(field),
        "unit": meta.get("unit", row.get("unit", "VND") if source else None),
        "period_basis": "annual_report" if source else None,
        "period_start": row.get("period_start"),
        "period_end": row.get("period_end"),
        "publication_as_of": meta.get("published_on"),
        "scope": row.get("scope"),
        "revision": row.get("revision"),
        "revision_status": meta.get("revision_status", "not_reported" if source else None),
        "semantic_limitation": (
            _SEMANTIC_UNPROVEN.get(field) or _OBSERVED_LIMITATIONS.get(field)
        ),
    }


def forensic_coverage(record: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """All currently modelled annual inputs, including missing/unsupported ones."""
    return {field: forensic_field_contract(record, field) for field in sorted(_FORENSIC_INPUTS)}


def ratio_field_contract(item_id: str, value: Any = None, *, period: str | None = None,
                         frequency: str | None = None,
                         quality: dict[str, Any] | None = None) -> dict[str, Any]:
    """Keep the reported number distinct from unverified financial measurement."""
    field = item_id.lower()
    known = field in _PERCENT_RATIOS | _VND_PER_SHARE | _PERIOD_END_MULTIPLES
    unit = ("percent" if field in _PERCENT_RATIOS else
            "VND/share" if field in _VND_PER_SHARE else
            "multiple" if field in _PERIOD_END_MULTIPLES else None)
    suspect = bool((quality or {}).get("suspected_placeholder"))
    present = _finite(value)
    # A finite reported value is a "supported" observation; the unverified
    # upstream formula and observation date stay disclosed below. A suspected
    # placeholder row downgrades to "partial"; an absent expected value is
    # "partial" as well (known field, missing number).
    status = ("partial" if suspect else "supported") if (known and present) else (
        "partial" if known else "unknown"
    )
    return {
        "field": item_id,
        "status": status,
        "value_present": present,
        "measurement_status": (
            "provider_formula_and_observation_as_of_unverified" if known else "unknown_item_id"
        ),
        "decision_eligible": False,
        "quality_status": "suspected" if suspect else None,
        "quality_note": (quality or {}).get("quality_note"),
        "source": "vnstock.Fundamental.equity.ratio" if known else None,
        "norm_id": None,
        "formula": None,  # upstream formula is not verified
        "unit": unit,
        "period_basis": "period_end_price" if field in _PERIOD_END_MULTIPLES else
                        "trailing_four_quarters" if field in {"trailing_eps", "roe_trailling"}
                        else "reported_period_ratio" if field in _PERCENT_RATIOS else
                        "reported_period_label" if known else None,
        "period": period,
        "frequency": frequency,
        "publication_as_of": None,
        "scope": None,
        "revision": None,
    }


def valuation_field_contract(field: str, output: dict[str, Any]) -> dict[str, Any]:
    """Carry observed valuation metadata without claiming price/EPS comparability."""
    if field not in {"price", "eps", "bvps", "per", "pb"}:
        return {"field": field, "status": "unknown", "source": None,
                "unit": None, "period_basis": None, "publication_as_of": None,
                "scope": None, "revision": None, "formula": None,
                "value_present": False, "measurement_status": "unknown_field",
                "decision_eligible": False}
    source = output.get({"price": "price_source", "eps": "eps_source",
                         "bvps": "bvps_source"}.get(field, ""))
    if field in {"per", "pb"}:
        source = "computed-local" if field in output else None
    value = output.get(field)
    present = _finite(value)
    # Registry-wide semantics: an observed finite value is "supported" (the
    # unverified dimensions stay in measurement_status, decision_eligible
    # False); a computed multiple stays "partial" (comparability gap); an
    # expected field with no value is "partial" (missing, disclosed).
    if field in {"per", "pb"}:
        status = "partial"
    elif field in {"price", "eps", "bvps"}:
        status = "supported" if present else "partial"
    else:
        status = "unknown"
    return {
        "field": field,
        "status": status,
        "value_present": present,
        "measurement_status": (
            "quote_timestamp_unit_adjustment_unverified" if field == "price" else
            "eps_period_unit_adjustment_unverified" if field == "eps" else
            "bvps_period_unit_adjustment_unverified" if field == "bvps" else
            "price_and_denominator_comparability_unverified"
        ),
        "decision_eligible": False,
        "source": source,
        "formula": {"per": "price / reported EPS if EPS > 0",
                    "pb": "price / reported BVPS if BVPS > 0"}.get(field),
        "unit": ("multiple" if field in {"per", "pb"} else
                 output.get(f"{field}_unit")),
        "period_basis": (output.get(f"{field}_basis") or
                         output.get(f"{field}_period")),
        "publication_as_of": None,
        "observation_as_of": output.get("price_as_of") if field in {"price", "per", "pb"} else None,
        "scope": None,
        "revision": None,
    }


def screener_field_contract(field: str, value: Any = None, *, period: str | None = None
                            ) -> dict[str, Any]:
    """Financial screener enrichment; market cap remains unsupported by source."""
    if field == "market_cap":
        status, source, unit, basis = "unknown", None, "VND expected", None
    elif field in {"pe", "roe"}:
        # finite enrichment is a supported observation; a missing one is the
        # disclosed partial gap (expected field, no number)
        present = _finite(value)
        status = "supported" if present else "partial"
        source = "vnstock.Fundamental.equity.ratio"
        unit = "multiple" if field == "pe" else "ratio"
        basis = "period_end_price" if field == "pe" else "reported_period_ratio"
    else:
        status, source, unit, basis = "unknown", None, None, None
    return {
        "field": field, "status": status, "source": source, "unit": unit,
        "value_present": _finite(value),
        "measurement_status": (
            "provider_formula_and_observation_as_of_unverified"
            if field in {"pe", "roe"} else "source_basis_unverified"
        ),
        "decision_eligible": False,
        "period_basis": basis, "period": period, "publication_as_of": None,
        "scope": None, "revision": None, "formula": None,
    }


def forensic_score_contract(field: str, output: dict[str, Any]) -> dict[str, Any]:
    """Distinguish an inapplicable industry model from a partial annual score."""
    model = output.get("beneish" if field == "m_score" else "piotroski", {})
    status = model.get("status") if field in _FORENSIC_FORMULAS else None
    if status == "complete":
        status = "supported"
    if status not in STATUS:
        status = "unknown"
    if output.get(field) is None and status == "supported":
        status = "partial"
    return {
        "field": field, "status": status,
        "source": "computed-local" if field in _FORENSIC_FORMULAS else None,
        "formula": _FORENSIC_FORMULAS.get(field),
        "unit": "score" if field in _FORENSIC_FORMULAS else None,
        "period_basis": "annual" if field in _FORENSIC_FORMULAS else None,
        "publication_as_of": None,
        "scope": model.get("scope"), "revision": None,
    }


def coverage_for_tool(tool: str, data: dict[str, Any]) -> dict[str, Any]:
    """Central read-only lookup for the currently mapped financial tool families.

    Pass the envelope's ``data``. A key absent from this registry is not assumed
    valid: it is represented by the individual field lookup as ``unknown``.
    This helper intentionally does not modify any public tool result.
    """
    if tool == "stock_forensic":
        annual = data.get("annual_inputs") or []
        newest = max(annual, key=lambda row: row.get("period_end") or "", default=None)
        inputs = forensic_coverage(newest) if newest is not None else None
        states = {item["status"] for item in inputs.values()} if inputs else set()
        if not states:
            inputs_status = "unknown"
        elif states == {"not_applicable"}:
            inputs_status = "not_applicable"
        elif "unknown" in states:
            inputs_status = "unknown"
        elif "partial" in states:
            inputs_status = "partial"
        else:
            inputs_status = "supported"
        return {
            "inputs": inputs,
            "inputs_status": inputs_status,
            "inputs_status_reason": (
                "requires_detail_true" if newest is None else "observed_input_coverage"
            ),
            "scores": {
                field: forensic_score_contract(field, data)
                for field in _FORENSIC_FORMULAS
            },
        }
    if tool == "valuation_run":
        return {field: valuation_field_contract(field, data)
                for field in ("price", "eps", "bvps", "per", "pb")}
    if tool == "financial_ratios":
        periods = data.get("periods") or []
        return {
            "coverage_scope": "all_reported_periods",
            "periods": {
                period: {
                    row["item_id"]: ratio_field_contract(
                        row["item_id"], (row.get("values") or {}).get(period),
                        period=period, frequency=data.get("frequency"),
                        quality=row,
                    )
                    for row in data.get("ratios") or []
                    if isinstance(row, dict) and isinstance(row.get("item_id"), str)
                }
                for period in periods
                if isinstance(period, str)
            },
            "peers": {
                peer["symbol"]: {
                    "period": peer.get("period_label"),
                    "fields": {
                        field: ratio_field_contract(
                            field, value, period=peer.get("period_label"),
                            frequency=peer.get("frequency"),
                            quality=(peer.get("metric_quality") or {}).get(field),
                        )
                        for field, value in (peer.get("values") or {}).items()
                    },
                    "error": peer.get("error"),
                }
                for peer in data.get("peers") or []
                if isinstance(peer, dict) and isinstance(peer.get("symbol"), str)
            },
        }
    if tool == "peer_compare":
        return {
            row["symbol"]: {
                field: ratio_field_contract(field, value, period=row.get("period_label"),
                                            frequency=row.get("frequency"),
                                            quality=(row.get("metric_quality") or {}).get(field))
                for field, value in row.items()
                if field not in {"symbol", "period_label", "frequency", "metric_quality",
                                 "metric_basis", "discarded_period_labels", "valuation_as_of",
                                 "error"}
            }
            for row in data.get("rows") or []
            if isinstance(row, dict) and isinstance(row.get("symbol"), str)
        }
    if tool == "stock_screener":
        return {
            row["symbol"]: {
                field: screener_field_contract(field, row.get(field),
                                                period=row.get("fundamentals_period"))
                for field in ("pe", "roe", "market_cap")
            }
            for row in data.get("candidates") or []
            if isinstance(row, dict) and isinstance(row.get("symbol"), str)
        }
    return {}


def financial_contract_reference() -> dict[str, Any]:
    """Public static reference; observation-dependent fields require a tool result.

    ``coverage_for_tool`` resolves each field against an actual response. The
    reference reports source IDs only where the provider map has evidence.
    """
    return {
        "schema_version": "financial-contract-registry-v1",
        "status_values": sorted(STATUS),
        "tools": ["stock_forensic", "valuation_run", "financial_ratios",
                  "peer_compare", "stock_screener"],
        "forensic_source_ids": {
            "financeinfo": dict(sorted(_FINANCEINFO_IDS.items())),
            "bctc": dict(sorted(_BCTC_IDS.items())),
        },
        "forensic_candidate_ids_not_live_verified": {
            "financeinfo": dict(sorted(_FINANCEINFO_CANDIDATES.items())),
        },
        "forensic_model_inputs_without_verified_mapping": sorted(
            _UNMAPPED | set(_SEMANTIC_UNPROVEN)
        ),
        "forensic_semantic_limitations": dict(sorted(_SEMANTIC_UNPROVEN.items())),
        "ratio_item_ids_with_documented_display_basis": sorted(
            _PERCENT_RATIOS | _VND_PER_SHARE | _PERIOD_END_MULTIPLES
        ),
        "screener_unsupported": ["market_cap"],
        "measurement_limits": [
            "financeinfo publication date and revision order unavailable",
            "BCTC publication applies only to matched enriched fields; revision order unavailable",
            "vnstock ratio item formula, publication, scope and revision unverified",
            "valuation quote price unit, timestamp and adjustment basis unverified",
            "current-TTM PE and current market-cap source not in this registry",
        ],
    }
