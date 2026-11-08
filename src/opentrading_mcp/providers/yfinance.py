"""yfinance provider (global indices, commodities, yield curve)."""

from __future__ import annotations

import re
from typing import Any

from opentrading_mcp.providers.circuit import guarded
from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable

GLOBAL_9 = ["^GSPC", "^IXIC", "^DJI", "^N225", "^HSI", "000001.SS", "^KS11", "^GDAXI", "^FTSE"]
WORLD_24 = [
    *GLOBAL_9,
    "^FCHI",
    "FTSE",
    "^STOXX50E",
    "^AXJO",
    "^TWII",
    "^STI",
    "^JKSE",
    "^NSEI",
    "9983196.TWO",
    "^MXX",
    "^BVSP",
    "^GSPTSE",
    "^TA125.TA",
    "^TASI",
]
REGIME_7 = ["^GSPC", "^VIX", "DX-Y.NYB", "^TNX", "BTC-USD", "GC=F", "CL=F"]
ORACLE_GROUPS = {
    "crypto": ["BTC-USD", "ETH-USD", "SOL-USD"],
    "metals": ["GC=F", "SI=F", "HG=F", "PL=F"],
    "energy": ["CL=F", "BZ=F", "NG=F"],
    "agri": ["ZC=F", "ZS=F", "KC=F", "CC=F"],
    "bonds_fx": ["^TNX", "DX-Y.NYB", "VND=X", "EURUSD=X"],
    "index": ["^GSPC", "^IXIC", "^N225", "^HSI", "^FTSE"],
}
COMMO_13 = [
    "GC=F",
    "SI=F",
    "CL=F",
    "HG=F",
    "PL=F",
    "PA=F",
    "BZ=F",
    "NG=F",
    "RB=F",
    "HO=F",
    "BTC-USD",
    "VND=X",
    "DX-Y.NYB",
]


@guarded("yfinance")
def batch_last(
    tickers: list[str], period: str = "2d", interval: str = "1d"
) -> list[dict[str, Any]]:
    """Batch last prices; period/interval pass yfinance spellings through."""
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ProviderUnavailable("yfinance not installed") from exc
    try:
        frame = yf.download(
            tickers, period=period, interval=interval, group_by="ticker", progress=False,
            timeout=25,
        )
    except Exception as exc:
        raise ProviderUnavailable("yfinance download failed") from exc
    out: list[dict[str, Any]] = []
    for ticker in tickers:
        try:
            series = frame[ticker]["Close"].dropna() if ticker in frame else None
            price = float(series.iloc[-1]) if series is not None and len(series) else None
            prev = float(series.iloc[-2]) if series is not None and len(series) > 1 else None
            out.append({"ticker": ticker, "price": price, "prev": prev})
        except Exception as exc:
            raise ProviderBadData(f"malformed yfinance series for {ticker}") from exc
    return out


@guarded("yfinance")
def yield_curve() -> dict[str, Any]:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ProviderUnavailable("yfinance not installed") from exc
    try:
        frame = yf.download(["^TNX", "2YY=F"], period="1d", progress=False, timeout=25)
        ten_y = float(frame["^TNX"]["Close"].dropna().iloc[-1]) / 100
        two_y = float(frame["2YY=F"]["Close"].dropna().iloc[-1]) / 100
    except Exception as exc:
        raise ProviderUnavailable("yfinance yield fetch failed") from exc
    return {"us10y": ten_y, "us2y": two_y, "inverted": two_y > ten_y}


@guarded("yfinance")
def world_indices(tickers: list[str] | None = None) -> list[dict[str, Any]]:
    return batch_last(tickers or WORLD_24)


# --- daily history: global indices, FX and gold (replaces vnstock fhsc/fmp routes) ---


def _finite(rec: Any, key: str, *, price: bool = True) -> float | None:
    """A finite cell. Prices come back as float32 (7678.72021484375): round to the
    7 significant digits float32 actually carries, so 7678.72 and 1.1228 both survive."""
    import math

    try:
        value = float(rec[key])
    except (KeyError, TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return float(f"{value:.7g}") if price else value


def _history_rows(frame: Any) -> list[dict[str, Any]]:
    """yfinance history frame → ascending {time, open, high, low, close, volume}
    rows (the shape the vnstock routes returned). NaN-close rows are dropped."""
    rows: list[dict[str, Any]] = []
    for stamp, rec in frame.iterrows():
        close = _finite(rec, "Close")
        if close is None:
            continue
        rows.append(
            {
                "time": stamp.date().isoformat() if hasattr(stamp, "date") else str(stamp)[:10],
                "open": _finite(rec, "Open"),
                "high": _finite(rec, "High"),
                "low": _finite(rec, "Low"),
                "close": close,
                "volume": _finite(rec, "Volume", price=False),
            }
        )
    rows.sort(key=lambda r: r["time"])
    return rows


@guarded("yfinance")
def history(ticker: str, count: int = 30) -> list[dict[str, Any]]:
    """The last ``count`` daily bars of one Yahoo ticker, oldest first."""
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ProviderUnavailable("yfinance not installed") from exc
    count = max(int(count), 1)
    # trading days → calendar days, with room for holidays and FX weekend rows
    days = int(count * 1.6) + 10
    try:
        frame = yf.Ticker(ticker).history(period=f"{days}d", interval="1d", auto_adjust=False)
    except Exception as exc:
        raise ProviderUnavailable(f"yfinance history failed: {ticker}: {exc}") from exc
    if frame is None or frame.empty:
        raise ProviderUnavailable(f"yfinance has no bars for {ticker}")
    rows = _history_rows(frame)
    if not rows:
        raise ProviderBadData(f"yfinance bars for {ticker} have no valid close")
    return rows[-count:]


# Common spellings (and the MSN-style codes the old vnstock route used, kept so
# existing callers keep working) → Yahoo tickers. Keys are normalised: upper
# case, no spaces, hyphens or dots ("S&P 500" → "S&P500"). Every target was
# checked live on 2026-11-09.
GLOBAL_INDEX_ALIASES = {
    **dict.fromkeys(("SPX", "GSPC", "^GSPC", "SP500", "S&P500", "S&P", "INX"), "^GSPC"),
    **dict.fromkeys(("DJIA", "DJI", "^DJI", "DOW", "DOWJONES", "USA30"), "^DJI"),
    **dict.fromkeys(("IXIC", "^IXIC", "NASDAQ", "NASDAQCOMPOSITE", "COMP"), "^IXIC"),
    **dict.fromkeys(("NDX", "^NDX", "NASDAQ100"), "^NDX"),
    **dict.fromkeys(("RUT", "^RUT", "RUSSELL2000"), "^RUT"),
    **dict.fromkeys(("RUI", "^RUI", "RUSSELL1000"), "^RUI"),
    **dict.fromkeys(("RUA", "^RUA", "RUSSELL3000"), "^RUA"),
    **dict.fromkeys(("NYA", "^NYA", "NYSE", "NYSECOMPOSITE"), "^NYA"),
    **dict.fromkeys(("FTSE", "FTSE100", "^FTSE", "UKX"), "^FTSE"),
    **dict.fromkeys(("DAX", "GDAXI", "^GDAXI"), "^GDAXI"),
    **dict.fromkeys(("CAC", "CAC40", "FCHI", "^FCHI", "PX1"), "^FCHI"),
    **dict.fromkeys(("NIKKEI", "NIKKEI225", "N225", "^N225"), "^N225"),
    **dict.fromkeys(("HANGSENG", "HSI", "^HSI"), "^HSI"),
    **dict.fromkeys(
        ("SHCOMP", "SSEC", "SHANGHAI", "SHANGHAICOMPOSITE", "000001", "000001SS"), "000001.SS"
    ),
    **dict.fromkeys(("SENSEX", "BSESN", "^BSESN"), "^BSESN"),
}
# Yahoo carries no VN-Index; the domestic index route does.
_VN_INDEX_SPELLINGS = frozenset({"VNI", "VNINDEX", "^VNINDEX", "VNINDEXVN"})
VALID_GLOBAL_SYMBOLS = (
    "S&P 500 (SPX/INX), Dow Jones (DJI/USA30), Nasdaq Composite (IXIC/COMP), Nasdaq-100 "
    "(NDX), Russell 2000/1000/3000 (RUT/RUI/RUA), NYSE Composite (NYA), FTSE 100 "
    "(FTSE/UKX), DAX, CAC 40 (CAC/PX1), Nikkei 225 (N225), Hang Seng (HSI), Shanghai "
    "Composite (000001/SHCOMP), SENSEX — or any Yahoo index ticker such as ^STOXX50E"
)


def normalize_global_symbol(symbol: str) -> str:
    """Map a spelling to its Yahoo ticker; unknown ``^`` tickers pass through."""
    raw = re.sub(r"[\s.\-]+", "", str(symbol)).upper()
    if raw in _VN_INDEX_SPELLINGS:
        raise ProviderBadData(
            f"{symbol!r} is the VN-Index: use vn_index_ohlcv (Yahoo has no VN-Index)"
        )
    if raw in GLOBAL_INDEX_ALIASES:
        return GLOBAL_INDEX_ALIASES[raw]
    ticker = str(symbol).strip().upper()
    if ticker.startswith("^") or ticker.endswith(".SS"):
        return ticker
    raise ProviderBadData(f"unknown global index {symbol!r}. Valid symbols: {VALID_GLOBAL_SYMBOLS}")


def global_index(symbol: str = "USA30", count: int = 30) -> list[dict[str, Any]]:
    """Daily bars of a world index (Yahoo), oldest first (#78)."""
    return history(normalize_global_symbol(symbol), count)


def fx_history(pair: str = "USDVND", count: int = 30) -> list[dict[str, Any]]:
    """Daily bars of a currency pair such as USDVND or EURUSD (Yahoo ``<pair>=X``)."""
    code = re.sub(r"[\s/\-]+", "", str(pair)).upper().removesuffix("=X")
    if not re.fullmatch(r"[A-Z]{6}", code):
        raise ProviderBadData(f"pair must be six letters like USDVND or EURUSD, got {pair!r}")
    return history(f"{code}=X", count)


# vn_msn_fx_gold legs. Yahoo has no spot gold (XAUUSD=X / XAU=X are empty,
# checked 2026-11-09): the gold leg is COMEX front-month futures, labelled so.
_FX_GOLD_LEGS: dict[str, dict[str, str]] = {
    "USDVND": {
        "ticker": "VND=X",
        "instrument": "spot_fx",
        "unit": "VND per USD",
        "note": "interbank USD/VND (Yahoo VND=X)",
    },
    "GC=F": {
        "ticker": "GC=F",
        "instrument": "futures",
        "unit": "USD per troy ounce",
        "note": (
            "COMEX gold futures, front month — NOT spot XAUUSD: futures trade above spot "
            "by the carry and roll between contracts"
        ),
    },
}
_FX_GOLD_ALIASES = {
    **dict.fromkeys(("USDVND", "VND", "VND=X", "USD/VND"), "USDVND"),
    **dict.fromkeys(("XAUUSD", "XAU", "GOLD", "GC", "GC=F"), "GC=F"),
}


def fx_gold(symbols: list[str] | None = None, days: int = 35) -> list[dict[str, Any]]:
    """USD/VND and world gold (futures) for gold-basis math (#79).

    Returns [{symbol, ticker, instrument, unit, note, points, last, series}].
    ``symbols`` accepts USDVND and XAUUSD/GOLD/GC (→ the GC=F futures leg);
    anything else is refused instead of silently dropped.
    """
    if symbols:
        unknown = [s for s in symbols if str(s).strip().upper() not in _FX_GOLD_ALIASES]
        if unknown:
            raise ProviderBadData(
                f"unsupported symbols {unknown}: this tool serves USDVND and gold "
                "(XAUUSD/GOLD/GC → COMEX GC=F futures); other pairs: vn_forex_ohlcv"
            )
        wanted = {_FX_GOLD_ALIASES[str(s).strip().upper()] for s in symbols}
    else:
        wanted = set(_FX_GOLD_LEGS)
    out: list[dict[str, Any]] = []
    for symbol, leg in _FX_GOLD_LEGS.items():
        if symbol not in wanted:
            continue
        rows = history(leg["ticker"], max(int(days), 5))
        out.append(
            {
                "symbol": symbol,
                **leg,
                "points": len(rows),
                "last": rows[-1] if rows else None,
                "series": rows[-35:],
            }
        )
    return out


@guarded("yfinance")
def oracle_markets(groups: list[str] | None = None) -> dict[str, Any]:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ProviderUnavailable("yfinance not installed") from exc
    wanted = {g.lower() for g in groups} if groups else None
    out: dict[str, Any] = {}
    for group, tickers in ORACLE_GROUPS.items():
        if wanted is not None and group.lower() not in wanted:
            continue
        try:
            frame = yf.download(
                tickers, period="1mo", interval="1d", group_by="ticker", progress=False,
                timeout=25,
            )
        except Exception as exc:
            raise ProviderUnavailable(f"yfinance oracle {group} failed") from exc
        items: list[dict[str, Any]] = []
        for ticker in tickers:
            try:
                series = frame[ticker]["Close"].dropna() if ticker in frame else None
                if series is None or len(series) == 0:
                    continue
                price = float(series.iloc[-1])
                ref = float(series.iloc[0])
                items.append(
                    {
                        "ticker": ticker,
                        "price": price,
                        "chg_30d": round((price - ref) / ref * 100, 2),
                        "high30": round(float(series.max()), 4),
                        "low30": round(float(series.min()), 4),
                    }
                )
            except Exception:
                continue
        out[group] = items
    return out


@guarded("yfinance")
def regime_assets() -> dict[str, Any]:
    try:
        import pandas as pd
        import yfinance as yf
    except ImportError as exc:
        raise ProviderUnavailable("yfinance not installed") from exc
    try:
        frame = yf.download(
            REGIME_7, period="2y", interval="1d", group_by="ticker", progress=False,
            timeout=60,
        )
    except Exception as exc:
        raise ProviderUnavailable("yfinance regime fetch failed") from exc
    out: dict[str, Any] = {}
    for ticker in REGIME_7:
        try:
            series = frame[ticker]["Close"].dropna() if ticker in frame else None
            if series is None or len(series) < 2:
                continue
            # One calendar year back, not 252 bars: BTC trades 7 days a week, so 252 bars
            # was about 8 months for it.
            year_ago = series[series.index <= series.index[-1] - pd.Timedelta(days=365)]
            base = float(year_ago.iloc[-1]) if len(year_ago) else None
            out[ticker] = {
                "last": float(series.iloc[-1]),
                "chg_1y_pct": round((float(series.iloc[-1]) - base) / base * 100, 2)
                if base
                else None,
            }
        except Exception:
            continue
    return out


@guarded("yfinance")
def mega_flows(top_n: int = 15) -> dict[str, Any]:
    leaders = [
        "AAPL",
        "MSFT",
        "NVDA",
        "AMZN",
        "GOOGL",
        "META",
        "TSLA",
        "AVGO",
        "TSM",
        "NFLX",
        "SAP",
        "ASML",
        "7203.T",
        "9984.T",
        "0700.HK",
        "9988.HK",
        "BABA",
        "005930.KS",
        "RELIANCE.NS",
        "0700.HK",
    ]
    return {"universe": "mega-cap leaders", "leaders": batch_last(leaders[: max(int(top_n), 1)])}


@guarded("yfinance")
def alloc_history(asset: str = "GC", timeframe: str = "1d") -> dict[str, Any]:
    symbols = {
        "GC": "GC=F",
        "VND": "VND=X",
        "BTC": "BTC-USD",
        "OIL": "CL=F",
        "SILVER": "SI=F",
        "COFFEE": "KC=F",
    }
    ticker = symbols.get(asset.upper(), "GC=F")
    interval = "1wk" if timeframe == "1wk" else "1d"
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ProviderUnavailable("yfinance not installed") from exc
    try:
        frame = yf.download(ticker, period="5y", interval=interval, progress=False, timeout=60)
    except Exception as exc:
        raise ProviderUnavailable(f"yfinance alloc {ticker} failed") from exc
    try:
        closes = frame["Close"].dropna()
        closes = closes[ticker] if ticker in closes.columns else closes
        points = [
            {"t": str(ts.date()), "c": round(float(v), 4)} for ts, v in closes.tail(60).items()
        ]
    except Exception as exc:
        raise ProviderBadData(f"malformed alloc series for {ticker}") from exc
    return {"asset": asset.upper(), "ticker": ticker, "points": points}


PINS_WORLD = [
    "^GSPC",
    "^IXIC",
    "^DJI",
    "^N225",
    "^HSI",
    "^FTSE",
    "BTC-USD",
    "GC=F",
    "CL=F",
    "VND=X",
]
PINS_VN = ["VCB", "HPG", "SSI", "VIC", "VHM"]


@guarded("yfinance")
def market_pins() -> dict[str, Any]:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ProviderUnavailable("yfinance not installed") from exc
    try:
        frame = yf.download(
            PINS_WORLD, period="5d", interval="1d", group_by="ticker", progress=False,
            timeout=25,
        )
    except Exception:
        return {"world": [], "vn": PINS_VN}
    pins: list[dict[str, Any]] = []
    for ticker in PINS_WORLD:
        try:
            closes = frame[ticker]["Close"].dropna() if ticker in frame else None
            if closes is None or len(closes) == 0:
                continue
            pins.append(
                {
                    "ticker": ticker,
                    "last": round(float(closes.iloc[-1]), 4),
                    "spark": [round(float(v), 4) for v in closes.tail(5)],
                }
            )
        except Exception:
            continue
    return {"world": pins, "vn": PINS_VN}


@guarded("yfinance")
def corp_actions(symbol: str) -> list[dict[str, Any]]:
    """Dividend + split history via yfinance actions (world tickers)."""
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ProviderUnavailable("yfinance not installed") from exc
    try:
        frame = yf.Ticker(symbol.upper()).actions
    except Exception as exc:
        raise ProviderUnavailable(f"yfinance actions failed: {symbol}") from exc
    if frame is None or len(frame) == 0:
        return []
    rows: list[dict[str, Any]] = []
    for ts, row in frame.iterrows():
        try:
            div = float(row.get("Dividends", 0.0) or 0.0)
        except (TypeError, ValueError):
            div = 0.0
        try:
            spl = float(row.get("Stock Splits", 0.0) or 0.0)
        except (TypeError, ValueError):
            spl = 0.0
        rows.append({"date": str(ts.date()), "dividends": div, "splits": spl})
    return rows


_HOLDER_ATTRS = {
    "major": "major_holders",
    "institutional": "institutional_holders",
    "mutualfund": "mutualfund_holders",
}


@guarded("yfinance")
def stock_holders(symbol: str, kind: str = "all") -> list[dict[str, Any]]:
    """Holder tables via yfinance (world tickers). kind: major|institutional|mutualfund|all."""
    if kind not in (*_HOLDER_ATTRS, "all"):
        raise ProviderBadData(f"unknown holder kind {kind!r}")
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ProviderUnavailable("yfinance not installed") from exc
    try:
        ticker = yf.Ticker(symbol.upper())
    except Exception as exc:
        raise ProviderUnavailable(f"yfinance ticker failed: {symbol}") from exc
    wanted = [kind] if kind in _HOLDER_ATTRS else sorted(_HOLDER_ATTRS)
    out: list[dict[str, Any]] = []
    for name in wanted:
        try:
            frame = getattr(ticker, _HOLDER_ATTRS[name])
        except Exception as exc:
            raise ProviderUnavailable(f"yfinance holders failed: {symbol}") from exc
        if frame is None or len(frame) == 0:
            continue
        try:
            records = frame.to_dict(orient="records")
        except Exception:
            continue
        for rec in records:
            clean_rec = {str(k): (None if str(v) == "nan" else v) for k, v in rec.items()}
            out.append({"kind": name, **clean_rec})
    return out
