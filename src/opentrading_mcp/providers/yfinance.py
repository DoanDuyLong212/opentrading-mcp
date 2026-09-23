"""yfinance provider (global indices, commodities, yield curve)."""

from __future__ import annotations

from typing import Any

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


def batch_last(tickers: list[str]) -> list[dict[str, Any]]:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ProviderUnavailable("yfinance not installed") from exc
    try:
        frame = yf.download(tickers, period="2d", interval="1d", group_by="ticker", progress=False)
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


def yield_curve() -> dict[str, Any]:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ProviderUnavailable("yfinance not installed") from exc
    try:
        ten_y = float(yf.Ticker("^TNX").history(period="1d")["Close"].iloc[-1]) / 100
        two_y = float(yf.Ticker("2YY=F").history(period="1d")["Close"].iloc[-1]) / 100
    except Exception as exc:
        raise ProviderUnavailable("yfinance yield fetch failed") from exc
    return {"us10y": ten_y, "us2y": two_y, "inverted": two_y > ten_y}


def world_indices() -> list[dict[str, Any]]:
    return batch_last(WORLD_24)


def oracle_markets() -> dict[str, Any]:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ProviderUnavailable("yfinance not installed") from exc
    groups: dict[str, Any] = {}
    for group, tickers in ORACLE_GROUPS.items():
        try:
            frame = yf.download(
                tickers, period="1mo", interval="1d", group_by="ticker", progress=False
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
        groups[group] = items
    return groups


def regime_assets() -> dict[str, Any]:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ProviderUnavailable("yfinance not installed") from exc
    try:
        frame = yf.download(REGIME_7, period="2y", interval="1d", group_by="ticker", progress=False)
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


def mega_flows() -> dict[str, Any]:
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
    return {"universe": "mega-cap leaders", "leaders": batch_last(leaders[:15])}


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
        frame = yf.download(ticker, period="5y", interval=interval, progress=False)
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


def market_pins() -> dict[str, Any]:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ProviderUnavailable("yfinance not installed") from exc
    pins: list[dict[str, Any]] = []
    for ticker in PINS_WORLD:
        try:
            hist = yf.Ticker(ticker).history(period="5d")
            closes = hist["Close"].dropna()
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
