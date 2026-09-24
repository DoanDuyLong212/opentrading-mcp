"""Screener columns catalog + local filters (P2, TradingView-pattern port).

No MongoDB. Pure local math over rows enriched from listing_symbols +
vn_fundamentals. Timezone handling lives in the tool envelope.
"""

from __future__ import annotations

from typing import Any

COLUMNS: dict[str, dict[str, str]] = {
    "symbol": {"group": "universe", "desc": "Ticker symbol (HOSE/HNX/UPCoM)."},
    "pe": {"group": "valuation", "desc": "Price / trailing earnings (P/E). Lower is cheaper."},
    "roe": {"group": "quality", "desc": "Return on equity, ratio 0..1 (e.g. 0.18 = 18%)."},
    "market_cap": {"group": "valuation", "desc": "Market capitalization in VND."},
    "sector": {"group": "universe", "desc": "Sector / ICB industry group name."},
    "industry": {"group": "universe", "desc": "Detailed industry name."},
    "index": {"group": "universe", "desc": "Index membership (e.g. VN30, VNMID)."},
    "close": {"group": "price", "desc": "Latest close price in VND."},
    "change_pct": {"group": "price", "desc": "Day change percent vs previous close."},
}

EQUALITY_FIELDS = {"sector", "industry", "index", "symbol", "exchange"}

RANGE_FIELDS = {"pe", "roe", "market_cap", "close", "change_pct"}


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
    if value is None or isinstance(value, bool):
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num


def apply_filters(
    rows: list[dict[str, Any]], filters: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """Filter rows locally.

    Range form: {field: [min, max]} with None as unbounded side.
    Equality form (sector/industry/index/symbol/exchange): plain string,
    case-insensitive. Unknown fields are ignored. Rows missing a filtered
    numeric value are excluded.
    """
    if not filters:
        return list(rows)
    out: list[dict[str, Any]] = []
    for row in rows:
        keep = True
        for field, cond in filters.items():
            if cond is None:
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
                    try:
                        if float(row.get(field)) != float(cond):  # type: ignore[arg-type]
                            keep = False
                            break
                    except (TypeError, ValueError):
                        keep = False
                        break
        if keep:
            out.append(row)
    return out
