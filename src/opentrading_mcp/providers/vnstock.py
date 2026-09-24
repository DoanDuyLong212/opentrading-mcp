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


def equity_trades(symbol: str, limit: int = 20) -> list[dict[str, Any]]:
    try:
        from vnstock import Market
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    try:
        frame = Market().equity(symbol.upper()).trades()
    except Exception as exc:
        raise ProviderUnavailable(f"vnstock trades failed: {symbol}") from exc
    rows = _records(frame)
    return rows[: max(limit, 1)]


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


def _records(frame: Any) -> list[dict[str, Any]]:
    try:
        rows = frame.to_dict(orient="records")
    except Exception:
        return []
    return [{str(k): v for k, v in r.items()} for r in rows]


def index_ohlcv(symbol: str = "VNINDEX", count: int = 100) -> list[dict[str, Any]]:
    try:
        from vnstock import Market
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    try:
        frame = Market().index(symbol.upper()).ohlcv(count=count, source="vci")
    except Exception as exc:
        raise ProviderUnavailable(f"vnstock index ohlcv failed: {symbol}") from exc
    rows = _records(frame)
    if not rows:
        raise ProviderUnavailable(f"no index bars for {symbol}")
    return rows


def equity_ohlcv(symbol: str, count: int = 100) -> list[dict[str, Any]]:
    try:
        from vnstock import Market
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    try:
        frame = Market().equity(symbol.upper()).ohlcv(count=count, source="vci")
    except Exception as exc:
        raise ProviderUnavailable(f"vnstock equity ohlcv failed: {symbol}") from exc
    rows = _records(frame)
    if not rows:
        raise ProviderUnavailable(f"no equity bars for {symbol}")
    return rows


def futures_ohlcv(symbol: str = "VN30F1M", count: int = 100) -> list[dict[str, Any]]:
    try:
        from vnstock import Market
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    try:
        frame = Market().futures(symbol.upper()).ohlcv(count=count)
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


def _pick_ratio_number(frame: Any, *needles: str) -> float | None:
    """Best-effort numeric pick from a vnstock ratio DataFrame.

    Handles both layouts: indicator as column or as index row.
    Returns the last non-null numeric value, else None.
    """
    try:
        cols = {str(c).lower(): c for c in frame.columns}
        for needle in needles:
            for key, col in cols.items():
                if needle in key:
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
            idx = {str(i).lower(): i for i in frame.index}
        except Exception:
            return None
        for needle in needles:
            for key, ix in idx.items():
                if needle in key:
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
        import pandas as pd  # type: ignore[import]

        if isinstance(data, pd.DataFrame) and len(data):
            pe = _pick_ratio_number(data, "pe", "p/e")
            roe = _pick_ratio_number(data, "roe")
            market_cap = _pick_ratio_number(
                data, "market_cap", "market cap", "von hoa", "vốn hóa"
            )
    except Exception:
        pass
    if isinstance(data, dict):
        lowered = {str(k).lower(): v for k, v in data.items()}
        for key, val in lowered.items():
            try:
                num = float(val)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            if pe is None and ("pe" in key or "p/e" in key):
                pe = num
            elif roe is None and "roe" in key:
                roe = num
            elif market_cap is None and ("market_cap" in key or "market cap" in key):
                market_cap = num
    if roe is not None and abs(roe) > 1:
        roe = roe / 100.0
    return {"symbol": symbol.upper(), "pe": pe, "roe": roe, "market_cap": market_cap}


_EXCHANGE_KEYS = ("exchange", "san", "floor", "exchangecode", "exchange_code")


def reference_equity(exchange: str = "HOSE") -> list[dict[str, Any]]:
    try:
        from vnstock import Reference
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    try:
        frame = Reference().equity.list()
    except Exception as exc:
        raise ProviderUnavailable("vnstock reference failed") from exc
    rows = _records(frame)
    query = exchange.upper()
    if query not in ("ALL", ""):
        lowered_keys = {k.lower(): k for r in rows for k in r}
        hit_key = next((lowered_keys[k] for k in _EXCHANGE_KEYS if k in lowered_keys), None)
        if hit_key is not None:
            rows = [r for r in rows if str(r.get(hit_key, "")).strip().upper() == query]
    return [{**r, "exchange": str(r.get("exchange") or exchange.upper()).upper()} for r in rows]


def company_info(symbol: str) -> dict[str, Any]:
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


def msn_fx_gold(days: int = 35) -> list[dict[str, Any]]:
    try:
        from vnstock.explorer import msn
    except ImportError as exc:
        raise ProviderUnavailable("vnstock msn explorer not installed") from exc
    from datetime import date, timedelta

    end = date.today().isoformat()
    start = (date.today() - timedelta(days=max(days, 5))).isoformat()
    out: list[dict[str, Any]] = []
    for symbol_id in ("USDVND", "XAUUSD"):
        try:
            frame = msn.Quote(symbol_id).history(start=start, end=end, interval="1D")
            rows = frame.to_dict(orient="records")
            out.append(
                {"symbol": symbol_id, "points": len(rows), "last": rows[-1] if rows else None}
            )
        except Exception as exc:
            raise ProviderUnavailable(f"vnstock msn failed: {symbol_id}: {exc}") from exc
    return out
