"""Financial ratio table from Vietstock financeinfo (replaces vnstock_quant.fa).

The owner stopped using the fhsc key (2026-11-08), and fhsc is the only source
of the statements ``vnstock_quant.fa`` computes from. Vietstock's financeinfo
page already carries a "Chỉ số tài chính" block — the numbers the v4 (KBS)
ratio table had, e.g. FPT 2025: P/E 15.91, ROE 28.3 %, EPS 6,021, BVPS 25,680 —
next to short income-statement and balance-sheet blocks. This module returns
them in the v4 table shape the tools read:

    {symbol, period, frequency, period_basis, periods (newest first),
     ratios: [{item_id, item, unit, values: {label: value}, basis, ...}],
     discarded_period_labels, source}

Measured 2026-11-09 (FPT, VCB; JWT session, no login):
- EPS ("EPS 4 quý") is trailing four quarters in BOTH year and quarter tables.
- P/E is the period-end price over that trailing EPS.
- In QUARTER tables ROE/ROA/ROS are the quarter's own figures (FPT ROE ≈ 7 %
  a quarter vs 28 % a year), not trailing — labelled ``single_quarter``.
- Banks have no ROS and no gross profit (different statement layout).

Derived rows (``derived: true``) are computed from same-period figures only:
P/B = P/E * EPS / BVPS (the period-end price over book value) and the gross
margin = gross profit / net revenue. Rows the source does not have stay as
explained all-None rows so callers filtering by id learn why.

The page needs the Vietstock login session (providers/vietstock.py); when the
session is rejected these tools fail together with financial_statements.
"""

from __future__ import annotations

import copy
import re
import threading
import time
from typing import Any

from opentrading_mcp.providers.errors import ProviderBadData

SOURCE = "vietstock.financeinfo"
_RATIO_SECTION = "Chỉ số tài chính"
_INCOME_SECTION = "Kết quả kinh doanh"

# Vietstock norm id → v4 item id, label, unit, and the basis per period kind.
_NORMS: dict[int, dict[str, Any]] = {
    53: {"item_id": "trailing_eps", "unit": "VND/share",
         "item": "Thu nhập trên mỗi cổ phần của 4 quý gần nhất (EPS)",
         "basis": {"year": "trailing_four_quarters", "quarter": "trailing_four_quarters"}},
    54: {"item_id": "book_value_per_share_bvps", "unit": "VND/share",
         "item": "Giá trị sổ sách của cổ phiếu (BVPS)",
         "basis": {"year": "period_end", "quarter": "period_end"}},
    55: {"item_id": "p_e", "unit": "times",
         "item": "Chỉ số giá thị trường trên thu nhập (P/E)",
         "basis": {"year": "period_end_price_over_trailing_eps",
                   "quarter": "period_end_price_over_trailing_eps"}},
    44: {"item_id": "net_profit_margin", "unit": "percent",
         "item": "Tỷ suất lợi nhuận ròng biên (ROS)",
         "basis": {"year": "reported_period_ratio", "quarter": "single_quarter"}},
    45: {"item_id": "roe", "unit": "percent",
         "item": "Tỷ suất lợi nhuận trên vốn chủ sở hữu bình quân (ROEA)",
         "basis": {"year": "reported_period_ratio", "quarter": "single_quarter"}},
    47: {"item_id": "roa", "unit": "percent",
         "item": "Tỷ suất lợi nhuận trên tổng tài sản bình quân (ROAA)",
         "basis": {"year": "reported_period_ratio", "quarter": "single_quarter"}},
}
_NET_REVENUE, _GROSS_PROFIT = 2216, 2217
# v4 ids Vietstock financeinfo does not carry: explained all-None rows.
_GAP_IDS = {
    "p_s": "Chỉ số giá thị trường trên doanh thu (P/S)",
    "ev_ebit": "EV/EBIT",
    "ev_ebitda": "EV/EBITDA",
    "ebit_margin": "Tỷ suất lợi nhuận EBIT biên",
    "dividend_yield": "Tỷ suất cổ tức",
    "roic": "Tỷ suất sinh lời trên vốn đầu tư (ROIC)",
    "beta": "Hệ số beta",
}
_GAP_NOTE = "not in Vietstock financeinfo — compute from prices or the annual report"

_TTL = 6 * 3600.0
_cache: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()


def period_sort_key(label: str) -> tuple[int, int]:
    """'2025' → (2025, 0); 'Q3/2026' → (2026, 3); anything else → (0, 0)."""
    text = str(label).strip()
    if re.fullmatch(r"\d{4}", text):
        return (int(text), 0)
    match = re.fullmatch(r"Q([1-4])/(\d{4})", text)
    if match:
        return (int(match.group(2)), int(match.group(1)))
    return (0, 0)


def _finite(value: Any) -> float | None:
    import math

    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def table_from_financeinfo(symbol: str, period: str, aligned: dict[str, Any]) -> dict[str, Any]:
    """Aligned financeinfo (``vietstock.align_financeinfo``) → v4 ratio table.

    Raises ProviderBadData when no usable period remains (#75: callers index
    ``periods[0]``) or when the page has no ratio block.
    """
    kind = "quarter" if period == "quarter" else "year"
    statements = aligned.get("statements") or {}
    ratio_rows = statements.get(_RATIO_SECTION) or []
    if not ratio_rows:
        raise ProviderBadData(f"Vietstock financeinfo has no ratio block for {symbol.upper()}")
    labels = [str(p) for p in aligned.get("periods") or []]
    discarded = sorted(p for p in labels if period_sort_key(p) == (0, 0))
    ordered = sorted(
        (p for p in labels if period_sort_key(p) != (0, 0)), key=period_sort_key, reverse=True
    )
    if not ordered:
        detail = f" (discarded labels: {', '.join(discarded)})" if discarded else ""
        raise ProviderBadData(
            f"Vietstock returned no usable {period} period for {symbol.upper()}{detail}"
        )

    def _values(row: dict[str, Any] | None) -> dict[str, float | None]:
        raw = (row or {}).get("values") or {}
        return {p: _finite(raw.get(p)) for p in ordered}

    by_norm = {int(r["norm_id"]): r for r in ratio_rows if r.get("norm_id") is not None}
    ratios: list[dict[str, Any]] = []
    for norm_id, spec in _NORMS.items():
        if norm_id not in by_norm:
            continue  # e.g. banks publish no ROS
        ratios.append(
            {
                "item_id": spec["item_id"],
                "item": spec["item"],
                "unit": spec["unit"],
                "values": _values(by_norm[norm_id]),
                "basis": spec["basis"][kind],
                "source_norm_id": norm_id,
            }
        )
    by_id = {r["item_id"]: r for r in ratios}

    # Derived, same-period only.
    pe, eps, bvps = (by_id.get(k, {}).get("values", {}) for k in
                     ("p_e", "trailing_eps", "book_value_per_share_bvps"))
    if pe and eps and bvps:
        ratios.append(
            {
                "item_id": "p_b",
                "item": "Chỉ số giá thị trường trên giá trị sổ sách (P/B)",
                "unit": "times",
                "values": {
                    p: (round(pe[p] * eps[p] / bvps[p], 2)
                        if None not in (pe[p], eps[p], bvps[p]) and bvps[p] > 0 else None)
                    for p in ordered
                },
                "basis": "period_end",
                "derived": True,
                "formula": "P/E * EPS(trailing) / BVPS — the period-end price over book value",
            }
        )
    income = {int(r["norm_id"]): r for r in statements.get(_INCOME_SECTION) or []
              if r.get("norm_id") is not None}
    if _NET_REVENUE in income and _GROSS_PROFIT in income:
        revenue, gross = _values(income[_NET_REVENUE]), _values(income[_GROSS_PROFIT])
        ratios.append(
            {
                "item_id": "gross_profit_margin",
                "item": "Tỷ suất lợi nhuận gộp biên",
                "unit": "percent",
                "values": {
                    p: (round(gross[p] / revenue[p] * 100.0, 2)
                        if None not in (gross[p], revenue[p]) and revenue[p] else None)
                    for p in ordered
                },
                "basis": "reported_period_ratio" if kind == "year" else "single_quarter",
                "derived": True,
                "formula": "gross profit / net revenue * 100",
            }
        )
    for item_id, item in _GAP_IDS.items():
        ratios.append(
            {"item_id": item_id, "item": item, "values": {p: None for p in ordered},
             "quality_note": _GAP_NOTE}
        )
    return {
        "symbol": symbol.upper(),
        "period": period,
        "frequency": "annual" if kind == "year" else "quarterly",
        "period_basis": "reported_period_label",
        "periods": ordered,
        "ratios": ratios,
        "discarded_period_labels": discarded,
        "source": SOURCE,
    }


def equity_ratios(symbol: str, period: str = "year") -> dict[str, Any]:
    """Ratio table for one symbol (6 h in-process cache; callers get a copy, so
    mutating a result can never poison later answers)."""
    from opentrading_mcp.providers import vietstock as vs_p

    if period not in ("year", "quarter"):
        raise ProviderBadData(f"unknown period {period!r} (year|quarter)")
    key = (symbol.upper(), period)
    with _cache_lock:
        hit = _cache.get(key)
        if hit is not None and time.monotonic() - hit[0] <= _TTL:
            return copy.deepcopy(hit[1])
    raw = vs_p.financeinfo(symbol.upper(), period)
    aligned, _warnings = vs_p.align_financeinfo(raw)
    table = table_from_financeinfo(symbol, period, aligned)
    with _cache_lock:
        _cache[key] = (time.monotonic(), table)
    return copy.deepcopy(table)


# equity_fundamentals output name → ratio-table item_id
_FUNDAMENTAL_CORE = {
    "pe": "p_e",
    "eps": "trailing_eps",
    "bvps": "book_value_per_share_bvps",
    "roe": "roe",
}


def equity_fundamentals(symbol: str, period: str = "year") -> dict[str, Any]:
    """Per-symbol PE/ROE/EPS/BVPS, every value from ONE report period (#76).

    The anchor is the newest period holding at least one core metric; a core
    metric missing there is None and listed in ``missing_in_period`` — never
    borrowed from an older period. ``roe`` is a fraction (0.283 = 28.3 %), as
    in v4. ``eps_basis`` follows the source row (Vietstock EPS is trailing four
    quarters in both tables); ``roe_basis`` says whether ROE is a full year or
    a single quarter.
    """
    table = equity_ratios(symbol, period)
    by_id = {r["item_id"]: r for r in table["ratios"]}

    def _value(item_id: str, label: str) -> float | None:
        row = by_id.get(item_id)
        return row["values"].get(label) if row else None

    anchor = next(
        (p for p in table["periods"]
         if any(_value(item_id, p) is not None for item_id in _FUNDAMENTAL_CORE.values())),
        None,
    )
    picked = {
        name: (_value(item_id, anchor) if anchor is not None else None)
        for name, item_id in _FUNDAMENTAL_CORE.items()
    }
    roe_pct = picked["roe"]
    return {
        "symbol": symbol.upper(),
        "pe": picked["pe"],
        "roe": roe_pct / 100.0 if roe_pct is not None else None,
        "market_cap": None,
        "market_cap_status": "missing_from_ratio_table",
        "eps": picked["eps"],
        "bvps": picked["bvps"],
        "period_label": anchor,
        "missing_in_period": sorted(k for k, v in picked.items() if v is None),
        "frequency": table["frequency"],
        "eps_basis": (by_id.get("trailing_eps") or {}).get("basis", "trailing_four_quarters"),
        "roe_basis": (by_id.get("roe") or {}).get("basis"),
        "discarded_period_labels": list(table.get("discarded_period_labels", [])),
        "source": SOURCE,
    }
