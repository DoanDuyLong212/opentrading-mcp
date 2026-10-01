"""vnstock provider (VCI/KBS/MSN). Direct fetch, no 8010 dependency."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable


def quote_history(symbol: str, days: int = 365) -> list[dict[str, Any]]:
    try:
        from vnstock import Quote
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    symbol = symbol.upper()
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=max(days, 5) + 30)).isoformat()
    frame = None
    for source in ("VCI", "KBS"):
        try:
            candidate = Quote(symbol=symbol, source=source).history(
                start=start, end=end, interval="1D"
            )
            if candidate is not None and len(candidate) > 0:
                frame = candidate
                break
        except Exception:
            continue
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


def equity_trades(
    symbol: str,
    limit: int = 20,
    board: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict[str, Any]]:
    try:
        from vnstock import Market
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    try:
        kwargs: dict[str, Any] = {}
        if board is not None:
            kwargs["board"] = board
        if from_date is not None:
            kwargs["from_date"] = from_date
        if to_date is not None:
            kwargs["to_date"] = to_date
        frame = Market().equity(symbol.upper()).trades(**kwargs)
    except Exception as exc:
        raise ProviderUnavailable(f"vnstock trades failed: {symbol}") from exc
    rows = _records(frame)
    return rows[: max(limit, 1)]


def listing_symbols(limit: int | None = None) -> list[dict[str, str]]:
    try:
        from vnstock import Listing
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    try:
        frame = Listing().all_symbols()
        rows = [
            {"symbol": str(r.get("symbol", "")), "name": str(r.get("organ_name", ""))}
            for r in frame.to_dict(orient="records")
        ]
        if limit is not None:
            rows = rows[: max(int(limit), 1)]
        return rows
    except Exception as exc:
        raise ProviderUnavailable("vnstock listing failed") from exc


def _records(frame: Any) -> list[dict[str, Any]]:
    try:
        rows = frame.to_dict(orient="records")
    except Exception:
        return []
    return [{str(k): v for k, v in r.items()} for r in rows]


def _clean(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Make provider rows JSON-safe: NaN/NaT/None -> None, exotic scalars -> str."""
    import math

    clean: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {}
        for key, val in row.items():
            try:
                if val is None:
                    item[key] = None
                elif isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                    item[key] = None
                elif isinstance(val, (str, int, bool)):
                    item[key] = val
                elif isinstance(val, float):
                    item[key] = val
                else:
                    text = str(val)
                    item[key] = None if text in ("NaT", "nan", "None", "") else text
            except Exception:
                item[key] = None
        clean.append(item)
    return clean


def index_ohlcv(
    symbol: str = "VNINDEX", count: int = 100, interval: str = "1D"
) -> list[dict[str, Any]]:
    try:
        from vnstock import Market
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    try:
        frame = Market().index(symbol.upper()).ohlcv(count=count, source="vci", resolution=interval)
    except Exception as exc:
        raise ProviderUnavailable(f"vnstock index ohlcv failed: {symbol}") from exc
    rows = _records(frame)
    if not rows:
        raise ProviderUnavailable(f"no index bars for {symbol}")
    return rows


def equity_ohlcv(symbol: str, count: int = 100, interval: str = "1D") -> list[dict[str, Any]]:
    try:
        from vnstock import Market
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    try:
        frame = (
            Market().equity(symbol.upper()).ohlcv(count=count, source="vci", resolution=interval)
        )
    except Exception as exc:
        raise ProviderUnavailable(f"vnstock equity ohlcv failed: {symbol}") from exc
    rows = _records(frame)
    if not rows:
        raise ProviderUnavailable(f"no equity bars for {symbol}")
    return rows


def futures_ohlcv(
    symbol: str = "VN30F1M", count: int = 100, interval: str = "1D"
) -> list[dict[str, Any]]:
    try:
        from vnstock import Market
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    try:
        frame = Market().futures(symbol.upper()).ohlcv(count=count, resolution=interval)
    except Exception as exc:
        raise ProviderUnavailable(f"vnstock futures ohlcv failed: {symbol}") from exc
    rows = _records(frame)
    if not rows:
        raise ProviderUnavailable(f"no futures bars for {symbol}")
    return rows


def forex_ohlcv(pair: str = "USDVND", count: int = 30) -> list[dict[str, Any]]:
    try:
        from vnstock import Market
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    try:
        frame = Market().forex(pair.upper()).ohlcv(count=count)
    except Exception as exc:
        raise ProviderUnavailable(f"vnstock forex failed: {pair}") from exc
    return _records(frame)


def crypto_ohlv(symbol: str = "BTCUSDT", count: int = 30) -> list[dict[str, Any]]:
    try:
        from vnstock import Market
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    try:
        frame = Market().crypto(symbol.upper()).ohlcv(count=count)
    except Exception as exc:
        raise ProviderUnavailable(f"vnstock crypto failed: {symbol}") from exc
    return _records(frame)


def global_index(symbol: str = "USA30", count: int = 30) -> list[dict[str, Any]]:
    try:
        from vnstock import Market
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    try:
        frame = Market().index(symbol.upper(), scope="global").ohlcv(count=count)
    except Exception as exc:
        raise ProviderUnavailable(f"vnstock global index failed: {symbol}") from exc
    return _records(frame)


def _norm_label(value: Any) -> str:
    """Normalize a frame label for exact matching: lower + non-alnum → '_'."""
    import re

    text = str(value).lower().strip()
    norm = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return norm or text


# Canonical alias sets (normalized form). Exact match only — never substring,
# so "pe" must NOT match "open" and "roe" must NOT match "growth".
PE_ALIASES = {"pe", "p_e", "pe_ttm", "pe_ratio", "price_earnings"}
ROE_ALIASES = {"roe", "roe_ttm", "return_on_equity"}
MARKET_CAP_ALIASES = {
    "market_cap",
    "marketcap",
    "total_market_cap",
    "market_capitalization",
    "von_hoa",
    "vonhoa",
    "v_n_h_a",
}


def _expand_aliases(want: set[str]) -> set[str]:
    out = set(want)
    if out & {"pe", "p_e"}:
        out |= PE_ALIASES
    if out & ROE_ALIASES:
        out |= ROE_ALIASES
    if out & MARKET_CAP_ALIASES:
        out |= MARKET_CAP_ALIASES
    return out


def _pick_ratio_number(frame: Any, *needles: str) -> float | None:
    """Best-effort numeric pick from a vnstock ratio DataFrame.

    Handles both layouts: indicator as column or as index row.
    Label matching is exact on the normalized label (lower, non-alnum → '_')
    against the needle alias set — never substring, so e.g. "pe" does not
    match an "open" column. Returns the last non-null numeric value, else None.
    """
    want = _expand_aliases({_norm_label(n) for n in needles})
    try:
        norm_cols = {_norm_label(c): c for c in frame.columns}
        for alias in want:
            col = norm_cols.get(alias)
            if col is None:
                continue
            try:
                series = frame[col].dropna()
            except Exception:
                continue
            if len(series):
                try:
                    return float(series.iloc[-1])
                except (TypeError, ValueError):
                    continue
        try:
            norm_idx = {_norm_label(i): i for i in frame.index}
        except Exception:
            return None
        for alias in want:
            ix = norm_idx.get(alias)
            if ix is None:
                continue
            try:
                row = frame.loc[ix].dropna()
            except Exception:
                continue
            if len(row):
                try:
                    return float(row.iloc[-1])
                except (TypeError, ValueError):
                    continue
    except Exception:
        return None
    return None


def equity_fundamentals(symbol: str, period: str = "year") -> dict[str, Any]:
    """Per-symbol PE/ROE/market-cap via vnstock Fundamental ratio.

    Best-effort parse: missing metrics come back as None, never raises
    for malformed frames (raises ProviderUnavailable only when the
    upstream call itself fails or vnstock is missing).
    """
    try:
        from vnstock import Fundamental
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    try:
        data = Fundamental().equity(symbol.upper()).ratio(period=period)
    except Exception as exc:
        raise ProviderUnavailable(f"vnstock fundamentals failed: {symbol}") from exc
    pe: float | None = None
    roe: float | None = None
    market_cap: float | None = None
    try:
        import pandas as pd

        if isinstance(data, pd.DataFrame) and len(data):
            pe = _pick_ratio_number(data, "pe", "p/e")
            roe = _pick_ratio_number(data, "roe")
            market_cap = _pick_ratio_number(data, "market_cap", "market cap", "von hoa", "vốn hóa")
    except Exception:
        pass
    if isinstance(data, dict):
        for raw_key, val in data.items():
            try:
                num = float(val)
            except (TypeError, ValueError):
                continue
            norm = _norm_label(raw_key)
            if pe is None and norm in PE_ALIASES:
                pe = num
            elif roe is None and norm in ROE_ALIASES:
                roe = num
            elif market_cap is None and norm in MARKET_CAP_ALIASES:
                market_cap = num
    if roe is not None and abs(roe) > 1:
        roe = roe / 100.0
    return {"symbol": symbol.upper(), "pe": pe, "roe": roe, "market_cap": market_cap}


_EXCHANGE_KEYS = ("exchange", "san", "floor", "exchangecode", "exchange_code")


def reference_equity(
    exchange: str = "HOSE", by: str = "exchange", key: str | None = None
) -> list[dict[str, Any]]:
    try:
        from vnstock import Reference
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    try:
        if by == "group":
            frame = Reference().equity.list_by_group(key or exchange)
            return _records(frame)
        if by == "industry":
            frame = Reference().equity.list_by_industry(key or exchange)
            return _records(frame)
        frame = None
        for source in ("KBS",):
            try:
                candidate = Reference().equity.list_by_exchange(source=source)
                if candidate is not None and len(candidate) > 0:
                    frame = candidate
                    break
            except Exception:
                continue
        if frame is None:
            frame = Reference().equity.list()
    except Exception as exc:
        raise ProviderUnavailable("vnstock reference failed") from exc
    rows = _records(frame)
    query = exchange.upper()
    if query not in ("ALL", ""):
        lowered_keys = {k.lower(): k for r in rows for k in r}
        hit_key = next((lowered_keys[k] for k in _EXCHANGE_KEYS if k in lowered_keys), None)
        if hit_key is None:
            # Fail-closed: never return unfiltered rows on schema drift.
            # The vn_reference tool maps ProviderBadData → unavailable envelope
            # with a warning, instead of silently returning the whole market.
            raise ProviderBadData(
                "reference frame has no exchange key; refusing unfiltered fallback"
            )
        rows = [r for r in rows if str(r.get(hit_key, "")).strip().upper() == query]
    return [{**r, "exchange": str(r.get("exchange") or exchange.upper()).upper()} for r in rows]


def company_info(symbol: str, detail: bool = False) -> dict[str, Any]:
    try:
        from vnstock import Company
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    try:
        client = Company(source="VCI", symbol=symbol.upper())
        info = client.info()
    except Exception as exc:
        raise ProviderUnavailable(f"vnstock company failed: {symbol}") from exc
    try:
        rows = info.to_dict(orient="records")
        data: dict[str, Any] = {"symbol": symbol.upper(), "info": rows[0] if rows else {}}
    except Exception:
        return {"symbol": symbol.upper(), "info": str(info)[:2000]}
    if not detail:
        return data
    for key, method in (("shareholders", "shareholders"), ("officers", "officers")):
        try:
            data[key] = _records(getattr(client, method)())
        except Exception:
            continue
    return data


def insider_trading(symbol: str, limit: int = 10) -> list[dict[str, Any]]:
    try:
        from vnstock import Company
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    frame = None
    for source in ("VCI", "KBS"):
        try:
            client = Company(source=source, symbol=symbol.upper())
            candidate = client.insider_trading()
            if candidate is not None:
                frame = candidate
                break
        except Exception:
            continue
    if frame is None:
        raise ProviderUnavailable(f"vnstock insider failed: {symbol}")
    rows = _records(frame)
    return rows[: max(limit, 1)]


def corp_events(symbol: str, limit: int = 20) -> list[dict[str, Any]]:
    """Corporate actions (cash dividends, share issues) via vnstock Company.

    Returns JSON-safe records, newest first as upstream orders them.
    """
    try:
        from vnstock import Company
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    frame = None
    for source in ("VCI", "KBS"):
        try:
            candidate = Company(source=source, symbol=symbol.upper()).events()
            if candidate is not None and len(candidate) > 0:
                frame = candidate
                break
        except Exception:
            continue
    if frame is None or len(frame) == 0:
        raise ProviderUnavailable(f"vnstock events failed: {symbol}")
    return _clean(_records(frame))[: max(limit, 1)]


def msn_fx_gold(symbols: list[str] | None = None, days: int = 35) -> list[dict[str, Any]]:
    try:
        from vnstock.explorer import msn
    except ImportError as exc:
        raise ProviderUnavailable("vnstock msn explorer not installed") from exc
    from datetime import date, timedelta

    end = date.today().isoformat()
    start = (date.today() - timedelta(days=max(days, 5))).isoformat()
    out: list[dict[str, Any]] = []
    for symbol_id in symbols or ("USDVND", "XAUUSD"):
        try:
            frame = msn.Quote(symbol_id).history(start=start, end=end, interval="1D")
            rows = frame.to_dict(orient="records")
            out.append(
                {"symbol": symbol_id, "points": len(rows), "last": rows[-1] if rows else None}
            )
        except Exception as exc:
            raise ProviderUnavailable(f"vnstock msn failed: {symbol_id}: {exc}") from exc
    return out
