"""Price-board rows from the project's DNSE client (replaces vnstock batch quote, #84).

vnstock 6 serves ``market.equity.quote`` only from fhsc/tcbs; the owner dropped
fhsc and has no tcbs key. The project's own signed DNSE client exposes, per
symbol and board (G1 = main board):

- ``/price/{sym}/secdef``         reference ("basic"), ceiling and floor;
- ``/price/{sym}/trades/latest``  last match, open/high/low, average, totals;
- ``/price/{sym}/quotes/latest``  three bid/offer levels.

This module turns them into the v4 board row the tools read (vnstock 4 KBS
shape: ``close_price`` etc. in DONG, ``volume_accumulated`` in shares).
Measured 2026-11-09 against the v4 baseline for FPT 2026-11-06: DNSE prices are
thousand dong (50.8 → 50,800), quantities are lots of 10 shares
(1,216,220 → 12,162,200 = v4 volume_accumulated; bid 12,230 → 122,300 = v4
bid_vol_1) and grossTradeAmount is billion dong (622.44945 → 622,449,450,000 =
v4 total_value).

Outside trading hours DNSE publishes the NEXT session's secdef (2026-11-06
20:26 for the 11-09 session) while trades/latest still holds the last session,
so its reference is not the traded session's. Then the traded session's
reference is the previous close (from candles; equal to the exchange reference
except on ex-rights days), ceiling/floor are None, and the next session's
values move to ``next_session`` — rather than reporting a 0 % change.
Foreign buy/sell volumes have no realtime source here and stay None.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable
from opentrading_mcp.units import INDEX_SYMBOLS

PRICE = 1000.0  # DNSE thousand dong → dong
LOT = 10  # DNSE quantity → shares
VALUE = 1e9  # DNSE billion dong → dong
_EXCHANGES = {"STO": "HOSE", "STX": "HNX", "UPX": "UPCOM", "HCX": "HOSE", "HNX": "HNX"}
_MAIN_BOARD = "G1"
_SESSION_END = "15:00"


def _board(rows: Any, key: str | None = None) -> dict[str, Any] | None:
    items = rows.get(key) if isinstance(rows, dict) and key else rows
    if not isinstance(items, list):
        return None
    main = [r for r in items if isinstance(r, dict) and r.get("boardId") == _MAIN_BOARD]
    return main[0] if main else None


def _dong(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number * PRICE, 2) if number > 0 else None


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_row(
    symbol: str,
    secdef: Any,
    trades: Any,
    quotes: Any,
    previous_close: Callable[[str, str], float | None],
) -> dict[str, Any]:
    """One v4 board row from the three DNSE payloads.

    ``previous_close(symbol, traded_day)`` returns the close (dong) of the
    session before ``traded_day``; it is only called outside trading hours.
    """
    trade = _board(trades, "trades")
    if trade is None:
        raise ProviderBadData(f"DNSE has no main-board trade for {symbol}")
    sec = _board(secdef)
    traded_at = str(trade.get("time") or "")
    traded_day = traded_at[:10]
    close = _dong(trade.get("matchPrice"))
    row: dict[str, Any] = {
        "symbol": symbol,
        # DNSE times are Vietnam local without an offset: say so.
        "time": f"{traded_at.replace(' ', 'T')}+07:00" if traded_at else None,
        "exchange": _EXCHANGES.get(str(trade.get("marketId")), trade.get("marketId")),
        "open_price": _dong(trade.get("openPrice")),
        "high_price": _dong(trade.get("highestPrice")),
        "low_price": _dong(trade.get("lowestPrice")),
        "close_price": close,
        "average_price": _dong(trade.get("avgPrice")),
        "volume_accumulated": (
            round(v * LOT) if (v := _num(trade.get("totalVolumeTraded"))) is not None else None
        ),
        "total_value": (
            round(v * VALUE) if (v := _num(trade.get("grossTradeAmount"))) is not None else None
        ),
        "foreign_buy_volume": None,
        "foreign_sell_volume": None,
        "source": "dnse",
    }
    sec_at = str((sec or {}).get("time") or "")
    next_session = bool(sec_at and traded_day and sec_at > f"{traded_day} {_SESSION_END}")
    if sec is not None and not next_session:
        reference = _dong(sec.get("basicPrice"))
        row["ceiling_price"] = _dong(sec.get("ceilingPrice"))
        row["floor_price"] = _dong(sec.get("floorPrice"))
    else:
        reference = previous_close(symbol, traded_day) if traded_day else None
        row["ceiling_price"] = None
        row["floor_price"] = None
        row["quote_note"] = (
            "market closed: reference is the previous close; ceiling/floor of the traded "
            "session are unknown, next_session holds the coming session's"
        )
        if sec is not None:
            row["next_session"] = {
                "reference_price": _dong(sec.get("basicPrice")),
                "ceiling_price": _dong(sec.get("ceilingPrice")),
                "floor_price": _dong(sec.get("floorPrice")),
                "published_at": sec_at,
            }
    row["reference_price"] = reference
    if close is not None and reference:
        row["price_change"] = round(close - reference, 2)
        row["percent_change"] = round((close - reference) / reference * 100.0, 4)
    else:
        row["price_change"] = None
        row["percent_change"] = None
    book = _board(quotes, "quotes")
    for side, key in (("bid", "bid"), ("ask", "offer")):
        levels = (book or {}).get(key) or []
        for n in range(1, 4):
            level = levels[n - 1] if len(levels) >= n and isinstance(levels[n - 1], dict) else {}
            qty = _num(level.get("quantity"))
            row[f"{side}_price_{n}"] = _dong(level.get("price"))
            row[f"{side}_vol_{n}"] = round(qty * LOT) if qty is not None else None
    return row


def _previous_close(symbol: str, traded_day: str) -> float | None:
    """Close (dong) of the session before ``traded_day``, from ssi/dnse candles."""
    from opentrading_mcp.providers import vnstock as vn_p

    try:
        candles = vn_p.quote_history(symbol, days=3)
    except Exception:
        return None
    earlier = [c for c in candles if str(c.get("t")) < traded_day]
    return round(float(earlier[-1]["c"]) * PRICE, 2) if earlier else None


def quote_row(symbol: str) -> dict[str, Any]:
    """Board row for one stock. Index codes are refused: they are not equities and
    an index read through an equity route comes back mis-scaled (#77)."""
    from opentrading_mcp.providers import dnse

    sym = symbol.strip().upper()
    if sym in INDEX_SYMBOLS:
        raise ProviderBadData(f"{sym} is an index code: use vn_index_ohlcv")
    trades = dnse._get(f"/price/{sym}/trades/latest")
    secdef = dnse._get(f"/price/{sym}/secdef")
    try:
        quotes = dnse._get(f"/price/{sym}/quotes/latest")
    except (ProviderUnavailable, ProviderBadData):
        quotes = None  # a row without depth beats no row
    return build_row(sym, secdef, trades, quotes, _previous_close)


def quote_rows(symbols: list[str]) -> list[dict[str, Any]]:
    """Rows for a chunk of symbols. A symbol that fails is reported in a trailing
    ``{"_missing": [...], "_errors": {...}}`` row (``split_batch`` reads it), never
    dropped silently. When every symbol fails, the first error is re-raised with
    its reason (missing DNSE keys → not_configured)."""
    from opentrading_mcp.failures import NOT_CONFIGURED

    rows: list[dict[str, Any]] = []
    errors: dict[str, str] = {}
    first: Exception | None = None
    for symbol in symbols:
        try:
            rows.append(quote_row(symbol))
        except Exception as exc:
            errors[symbol.strip().upper()] = str(exc)[:160]
            first = first or exc
    if symbols and not rows:
        detail = "; ".join(f"{s}: {e}" for s, e in errors.items())[:300]
        reason = getattr(first, "reason", None)
        if reason is None and "not set" in str(first):
            reason = NOT_CONFIGURED
        raise ProviderUnavailable(f"DNSE board failed: {detail}", reason=reason) from first
    if errors:
        rows.append({"_missing": sorted(errors), "_errors": errors})
    return rows
