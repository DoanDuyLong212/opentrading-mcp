"""vnstock provider (VCI/KBS/MSN). Direct fetch, no 8010 dependency."""

from __future__ import annotations

from typing import Any

from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable


def quote_history(symbol: str, days: int = 365) -> list[dict[str, Any]]:
    try:
        from vnstock import Quote
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    symbol = symbol.upper()
    for source in ("VCI", "KBS"):
        try:
            frame = Quote(symbol=symbol, source=source).history(start=None, end=None, interval="1D")
            break
        except Exception:
            frame = None
    else:
        frame = None
    if frame is None or len(frame) == 0:
        raise ProviderUnavailable(f"no candles for {symbol}")
    try:
        tail = frame.tail(max(days, 1))
        rows: list[dict[str, Any]] = []
        for ts, row in tail.iterrows():
            rows.append(
                {
                    "t": str(ts),
                    "o": float(row.get("open", 0)),
                    "h": float(row.get("high", 0)),
                    "l": float(row.get("low", 0)),
                    "c": float(row.get("close", 0)),
                    "v": float(row.get("volume", 0)),
                }
            )
        return rows
    except Exception as exc:
        raise ProviderBadData(f"malformed vnstock frame for {symbol}") from exc


def equity_quote_batch(symbols: list[str]) -> list[dict[str, Any]]:
    try:
        from vnstock import Market
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    try:
        frame = Market().equity(symbols).quote()
    except Exception as exc:
        raise ProviderUnavailable("vnstock batch quote failed") from exc
    out: list[dict[str, Any]] = []
    try:
        records = frame.to_dict(orient="records")
    except Exception:
        records = []
    for record in records:
        out.append({str(k): record[k] for k in record})
    return out


def listing_symbols() -> list[dict[str, str]]:
    try:
        from vnstock import Listing
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    try:
        frame = Listing().all_symbols()
        return [
            {"symbol": str(r.get("symbol", "")), "name": str(r.get("organ_name", ""))}
            for r in frame.to_dict(orient="records")
        ]
    except Exception as exc:
        raise ProviderUnavailable("vnstock listing failed") from exc
