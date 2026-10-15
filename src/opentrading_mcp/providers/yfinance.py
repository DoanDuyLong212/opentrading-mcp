"""yfinance provider (global indices, commodities, yield curve)."""

from __future__ import annotations

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
            out[ticker] = {
                "last": float(series.iloc[-1]),
                "chg_1y_pct": round(
                    (float(series.iloc[-1]) - float(series.iloc[-252]))
                    / float(series.iloc[-252])
                    * 100,
                    2,
                )
                if len(series) >= 252
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
