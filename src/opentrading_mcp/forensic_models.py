"""Strict annual forensic models; IO and source normalization live in providers.forensic.

Beneish/Lee/Nichols (2013), Appendix A: eight variables, CFO-based TATA.
Piotroski (2000) §§2.3.1-2.3.3: beginning assets for ROA/CFO/turnover;
long-term debt including current portion divided by average assets for leverage.
Primary sources:
https://cpb-us-w2.wpmucdn.com/sites.udel.edu/dist/a/855/files/2020/07/Earnings-Manipulation-and-Expected-Returns.pdf
https://www.ivey.uwo.ca/media/3775523/value_investing_the_use_of_historical_financial_statement_information.pdf

Synthetic callers may supply depreciation, current_portion_long_term_debt and
an explicit boolean equity_issued. These are NOT claimed as verified source IDs.
"""

from __future__ import annotations

from typing import Any

from opentrading_mcp.providers.forensic import (
    BUSINESS_TYPES,
    finite_number,
    select_annual_window,
)

SCHEMA_VERSION = "annual-forensic-v1"
BENEISH_VERSION = "beneish-8-cfo-2013-appendix-a-net-ppe-v3"
PIOTROSKI_VERSION = "piotroski-9-2000-beginning-assets-v1"
BENEISH_INTERCEPT = -4.84
BENEISH_COEF = {
    "dsri": 0.920,
    "gmi": 0.528,
    "aqi": 0.404,
    "sgi": 0.892,
    "depi": 0.115,
    "sgai": -0.172,
    "tata": 4.679,
    "lvgi": -0.327,
}
_FLOW_FIELDS = {"revenue", "gross", "cogs", "net_income", "selling", "admin"}


class _Inputs:
    def __init__(self, window: dict[str, Any]):
        self.window = window
        self.missing: set[str] = set()
        self.sources: dict[str, Any] = {}

    def get(self, period: str, key: str, *, signed: bool = False) -> Any:
        name = f"{period}.{key}"
        record = self.window.get(period)
        statement = "LCTT" if key == "cfo" else "KQKD" if key in _FLOW_FIELDS else "CDKT"
        value = (record or {}).get("values", {}).get(key)
        if record is None or statement not in record.get("statements", []):
            value = None
        valid = isinstance(value, bool) if key == "equity_issued" else finite_number(value)
        if key == "assets" and valid and value <= 0:
            valid = False
        if key != "equity_issued" and valid and not signed and value < 0:
            valid = False
        if not valid:
            self.missing.add(name)
            return None
        self.sources[name] = {
            "source": record["source"],
            "period_start": record["period_start"],
            "period_end": record["period_end"],
            "scope": record["scope"],
            "company_id": record["company_id"],
            "revision": record.get("revision"),
            **record.get("input_provenance", {}).get(key, {}),
        }
        return value

    def div(self, numerator: Any, denominator: Any, name: str) -> Any:
        if numerator is None or denominator is None:
            return None
        if denominator <= 0:
            self.missing.add(f"invalid.{name}.denominator")
            return None
        try:
            value = numerator / denominator
        except (OverflowError, ZeroDivisionError):
            value = None
        if not finite_number(value):
            self.missing.add(f"invalid.{name}.nonfinite")
            return None
        return value

    def add(self, *values: Any) -> Any:
        if any(v is None for v in values):
            return None
        value = sum(values)
        if not finite_number(value):
            self.missing.add("invalid.sum.nonfinite")
            return None
        return value

    def gross(self, period: str) -> Any:
        record = self.window.get(period) or {}
        if "gross" in record.get("values", {}):
            return self.get(period, "gross", signed=True)
        revenue, cogs = self.get(period, "revenue"), self.get(period, "cogs")
        return None if revenue is None or cogs is None else revenue - cogs


def calculate_forensic(bundle: dict[str, Any]) -> dict[str, Any]:
    """Calculate only compatible annual inputs; missing never becomes zero/failure."""
    window = select_annual_window(bundle)
    current = window.get("current") or {}
    business_type = current.get("business_type", "unknown")
    # Classification diagnostics may survive a rejected latest report. Never use
    # an older report's values as the current annual model inputs.
    if not current:
        observed_types = {r.get("business_type", "unknown") for r in bundle.get("records", [])}
        for diagnostic in bundle.get("diagnostics", []):
            raw_type = diagnostic.get("header", {}).get("BusinessType")
            observed_types.add(
                BUSINESS_TYPES.get(raw_type, "unknown")
                if isinstance(raw_type, int) and not isinstance(raw_type, bool)
                else "unknown"
            )
        if len(observed_types) == 1:
            business_type = next(iter(observed_types))
    financial = business_type in {"bank", "securities", "insurance"}
    known = business_type == "general"
    inputs = _Inputs(window)
    # The same denominator definition is mandatory in both annual periods.
    # A net/gross switch changes DEPI while hiding a data gap.
    # Appendix A, Exhibit A1 defines PPE [8] as net in the AQI row and uses
    # that same item [8] for DEPI's Depreciation/(Depreciation + PPE) rate.
    # A later prose sentence calls it gross PP&E; this explicit version follows
    # the equation/table, without switching definitions across annual periods.
    depi_basis = "net_ppe"

    def ratio(period: str, numerator: str, denominator: str, *, signed: bool = False):
        return inputs.div(
            inputs.get(period, numerator, signed=signed),
            inputs.get(period, denominator),
            f"{period}.{numerator}/{denominator}",
        )

    def margins(period: str, *, beneish_domain: bool = False):
        margin = inputs.div(
            inputs.gross(period), inputs.get(period, "revenue"), f"{period}.gross_margin"
        )
        # Beneish's ratio-of-margins excludes negative margins in this strict
        # model policy. Piotroski compares signed margins, including improvements
        # from a negative base. Prior zero GMI remains a valid numerator.
        if beneish_domain and margin is not None and margin < 0:
            inputs.missing.add(f"invalid.{period}.gross_margin.negative")
            return None
        return margin

    def aquality(period: str):
        share = inputs.div(
            inputs.add(inputs.get(period, "current_assets"), inputs.get(period, "net_ppe")),
            inputs.get(period, "assets"),
            f"{period}.asset_quality",
        )
        if share is not None and share > 1:
            inputs.missing.add(f"invalid.{period}.asset_quality.negative")
            return None
        return None if share is None else 1 - share

    def depreciation_rate(period: str):
        dep = inputs.get(period, "depreciation")
        net_ppe = inputs.get(period, "net_ppe")
        return inputs.div(dep, inputs.add(dep, net_ppe), f"{period}.depreciation_rate")

    def beneish_leverage(period: str):
        debt = inputs.add(
            inputs.get(period, "long_term_debt"), inputs.get(period, "current_liabilities")
        )
        return inputs.div(debt, inputs.get(period, "assets"), f"{period}.beneish_leverage")

    def sg_expense(period: str):
        return inputs.div(
            inputs.add(inputs.get(period, "selling"), inputs.get(period, "admin")),
            inputs.get(period, "revenue"),
            f"{period}.sga",
        )

    def tata():
        ni, cfo = (
            inputs.get("current", "net_income", signed=True),
            inputs.get("current", "cfo", signed=True),
        )
        return inputs.div(
            None if ni is None or cfo is None else ni - cfo, inputs.get("current", "assets"), "tata"
        )

    operations = {
        "dsri": lambda: inputs.div(
            ratio("current", "receivables", "revenue"),
            ratio("previous", "receivables", "revenue"),
            "dsri",
        ),
        "gmi": lambda: inputs.div(
            margins("previous", beneish_domain=True), margins("current", beneish_domain=True), "gmi"
        ),
        "aqi": lambda: inputs.div(aquality("current"), aquality("previous"), "aqi"),
        "sgi": lambda: inputs.div(
            inputs.get("current", "revenue"), inputs.get("previous", "revenue"), "sgi"
        ),
        "depi": lambda: inputs.div(
            depreciation_rate("previous"), depreciation_rate("current"), "depi"
        ),
        "sgai": lambda: inputs.div(sg_expense("current"), sg_expense("previous"), "sgai"),
        "tata": tata,
        "lvgi": lambda: inputs.div(
            beneish_leverage("current"), beneish_leverage("previous"), "lvgi"
        ),
    }
    indexes, component_missing = {}, {}
    for key, operation in operations.items():
        inputs.missing = set()
        indexes[key] = operation()
        component_missing[key] = sorted(inputs.missing)
    beneish_sources = dict(inputs.sources)
    m_missing = sorted({m for values in component_missing.values() for m in values})
    if not known:
        m_missing.append("business_type.general")
    m_score = None
    raw_m_score = None
    if known and not m_missing and all(v is not None for v in indexes.values()):
        raw_score = BENEISH_INTERCEPT + sum(BENEISH_COEF[k] * v for k, v in indexes.items())
        if finite_number(raw_score):
            raw_m_score = float(raw_score)  # classification uses raw precision
            m_score = round(raw_score, 4)  # display rounding only
        else:
            m_missing.append("invalid.m_score.nonfinite")

    def roa(period: str, beginning: str):
        return inputs.div(
            inputs.get(period, "net_income", signed=True),
            inputs.get(beginning, "assets"),
            f"{period}.roa",
        )

    def cfo_ratio():
        return inputs.div(
            inputs.get("current", "cfo", signed=True),
            inputs.get("previous", "assets"),
            "current.cfo/assets",
        )

    def leverage(period: str, beginning: str):
        debt = inputs.add(
            inputs.get(period, "long_term_debt"),
            inputs.get(period, "current_portion_long_term_debt"),
        )
        total = inputs.add(inputs.get(period, "assets"), inputs.get(beginning, "assets"))
        return inputs.div(debt, None if total is None else total / 2, f"{period}.leverage")

    def compare(left: Any, right: Any):
        return None if left is None or right is None else left > right

    def turnover(period: str, beginning: str):
        return inputs.div(
            inputs.get(period, "revenue"), inputs.get(beginning, "assets"), f"{period}.turnover"
        )

    def no_issuance():
        issued = inputs.get("current", "equity_issued")
        return None if issued is None else not issued

    signals = {
        "positive_roa": lambda: compare(roa("current", "previous"), 0),
        "positive_cfo": lambda: compare(cfo_ratio(), 0),
        "roa_increased": lambda: compare(roa("current", "previous"), roa("previous", "beginning")),
        "cfo_above_roa": lambda: compare(cfo_ratio(), roa("current", "previous")),
        "leverage_decreased": lambda: compare(
            leverage("previous", "beginning"), leverage("current", "previous")
        ),
        "current_ratio_increased": lambda: compare(
            ratio("current", "current_assets", "current_liabilities"),
            ratio("previous", "current_assets", "current_liabilities"),
        ),
        "no_equity_issuance": no_issuance,
        "gross_margin_increased": lambda: compare(margins("current"), margins("previous")),
        "turnover_increased": lambda: compare(
            turnover("current", "previous"), turnover("previous", "beginning")
        ),
    }
    inputs.sources = {}
    components = {}
    for key, operation in signals.items():
        inputs.missing = set()
        value = operation()
        components[key] = {"passed": value, "missing_inputs": sorted(inputs.missing)}
    f_missing = sorted({m for c in components.values() for m in c["missing_inputs"]})
    if not known:
        f_missing.append("business_type.general")
    passed = sum(c["passed"] is True for c in components.values())
    evaluated = sum(c["passed"] is not None for c in components.values())
    f_score = f"{passed}/9" if known and evaluated == 9 and not f_missing else None

    def metadata(version: str, labels: tuple[str, ...]):
        return {
            "version": version,
            "basis": "annual",
            "scope": window["report_scope"],
            "periods_used": {
                key: {"start": window[key]["period_start"], "end": window[key]["period_end"]}
                for key in labels
                if window.get(key)
            },
        }

    beneish = {
        **metadata(BENEISH_VERSION, ("current", "previous")),
        "status": "not_applicable"
        if financial
        else "complete"
        if m_score is not None
        else "partial",
        "score": m_score,
        "indexes": indexes,
        "depi_denominator": depi_basis,
        "missing_inputs": m_missing,
        "component_missing": component_missing,
        "input_sources": beneish_sources,
        "cutoff": -1.78 if m_score is not None else None,
    }
    piotroski = {
        **metadata(PIOTROSKI_VERSION, ("current", "previous", "beginning")),
        "status": "unsupported" if financial else "complete" if f_score is not None else "partial",
        "score": f_score,
        "passed": passed,
        "evaluated": evaluated,
        "components": components,
        "missing_inputs": f_missing,
        "input_sources": inputs.sources,
        "turnover_basis": "sales / beginning total assets (§2.3.3)",
    }
    flags = []
    if raw_m_score is not None and raw_m_score > -1.78:
        flags.append("M-Score above -1.78: further review warranted; not a fraud conclusion")
    return {
        "symbol": bundle.get("symbol"),
        "schema_version": SCHEMA_VERSION,
        "basis": "annual",
        "business_type": business_type,
        **{k: round(v, 4) if v is not None else None for k, v in indexes.items()},
        "m_score": m_score,
        "m_partial": m_missing or None,
        "f_score": f_score,
        "f_missing": f_missing or None,
        "f_passed": passed,
        "f_evaluated": evaluated,
        "f_components": components,
        "beneish": beneish,
        "piotroski": piotroski,
        "flags": flags,
        "data_time": current.get("period_end"),
        "window_missing": window["missing_inputs"],
    }
