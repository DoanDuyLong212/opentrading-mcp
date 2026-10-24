"""Screener columns catalog + local filters (P2, TradingView-pattern port).

No MongoDB. Pure local math over rows enriched from listing_symbols +
vn_fundamentals. Timezone handling lives in the tool envelope.
"""

from __future__ import annotations

import math
from typing import Any

from pandas.api.types import is_bool

COLUMNS: dict[str, dict[str, str]] = {
    "symbol": {"group": "universe", "desc": "Ticker symbol (HOSE/HNX/UPCoM)."},
    "pe": {
        "group": "valuation",
        "desc": "Price / trailing earnings (P/E). Lower is cheaper. A filter with only an "
        "upper bound keeps pe > 0: a negative P/E (a loss) is not a cheap valuation. Give "
        "an explicit lower bound (e.g. [-5, 10]) to include losses.",
    },
    "roe": {"group": "quality", "desc": "Return on equity, ratio 0..1 (e.g. 0.18 = 18%)."},
    "market_cap": {"group": "valuation", "desc": "Market capitalization in VND."},
    "sector": {
        "group": "universe",
        "desc": "Sector / ICB industry group name. Non-filterable "
        "(universe rows are not enriched with sector yet; sector filters are ignored).",
    },
    "industry": {
        "group": "universe",
        "desc": "Detailed industry name. Non-filterable "
        "(universe rows are not enriched with industry yet; industry filters are ignored).",
    },
    "index": {
        "group": "universe",
        "desc": "Index membership (e.g. VN30, VNMID). Non-filterable "
        "(universe rows are not enriched with index membership yet; index filters are ignored).",
    },
    "close": {
        "group": "price",
        "desc": "Latest close price in VND. Catalog-only, non-filterable "
        "(stock_screener has no live price enrichment; price filters are ignored).",
    },
    "change_pct": {
        "group": "price",
        "desc": "Day change percent vs previous close. Catalog-only, non-filterable "
        "(stock_screener has no live price enrichment; price filters are ignored).",
    },
}

EQUALITY_FIELDS = {"sector", "industry", "index", "symbol", "exchange"}

RANGE_FIELDS = {"pe", "roe", "market_cap", "close", "change_pct"}

# Fields where an upper bound without a lower bound also requires a positive value.
# A negative P/E means the company made a loss (NVL 2024: -3.1), so "pe <= 10" must
# not read it as cheap. An explicit lower bound is the caller's choice and is honoured.
# This mirrors common screener practice; drop "pe" here to let losses through.
POSITIVE_WHEN_CAPPED = {"pe"}

# Price group is catalog-only (no live quote enrichment in stock_screener),
# so price filters would be dead-filters. Equality fields sector/industry/index
# are documented in the catalog but universe data is not enriched with them yet,
# so matching would silently drop every row. Both are non-filterable: apply_filters
# ignores them instead of excluding every row.
NON_FILTERABLE_FIELDS = {"close", "change_pct", "sector", "industry", "index"}

KNOWN_FIELDS = set(COLUMNS) | EQUALITY_FIELDS | RANGE_FIELDS


def screener_columns(
    group: str | None = None, search: str | None = None
) -> dict[str, dict[str, str]]:
    """Return catalog subset filtered by group and/or free-text search."""
    out: dict[str, dict[str, str]] = {}
    for name, meta in COLUMNS.items():
        if group and str(meta.get("group", "")).lower() != group.lower():
            continue
        if search:
            needle = search.lower()
            hay = f"{name} {meta.get('group', '')} {meta.get('desc', '')}".lower()
            if needle not in hay:
                continue
        out[name] = dict(meta)
    return out


def _as_number(value: Any) -> float | None:
    if value is None or is_bool(value):
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num if math.isfinite(num) else None


def apply_filters(
    rows: list[dict[str, Any]], filters: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """Filter rows locally.

    Range form: {field: [min, max]} with None as unbounded side.
    Equality form (symbol/exchange): plain string, case-insensitive. Unknown
    fields, and non-filterable fields (catalog-only price fields close/change_pct;
    sector/industry/index not yet present in universe rows) are ignored. Rows
    missing a filtered numeric value are excluded.
    """
    if not filters:
        return list(rows)
    out: list[dict[str, Any]] = []
    for row in rows:
        keep = True
        for field, cond in filters.items():
            if cond is None:
                continue
            if field in NON_FILTERABLE_FIELDS:
                continue
            if field not in KNOWN_FIELDS:
                continue
            if isinstance(cond, (list, tuple)) and len(cond) == 2:
                lo, hi = cond
                if lo is None and hi is None:
                    continue
                num = _as_number(row.get(field))
                if num is None:
                    keep = False
                    break
                if lo is not None and num < float(lo):
                    keep = False
                    break
                if (
                    hi is not None and lo is None
                    and field in POSITIVE_WHEN_CAPPED and num <= 0
                ):
                    keep = False
                    break
                if hi is not None and num > float(hi):
                    keep = False
                    break
            else:
                if field in EQUALITY_FIELDS or field not in RANGE_FIELDS:
                    want = str(cond).strip()
                    if not want or want.upper() in ("ALL", "*"):
                        continue
                    got = row.get(field)
                    if got is None or str(got).strip().upper() != want.upper():
                        keep = False
                        break
                else:
                    num, target = _as_number(row.get(field)), _as_number(cond)
                    if num is None or target is None or num != target:
                        keep = False
                        break
        if keep:
            out.append(row)
    return out
