"""yfinance provider (global indices, commodities, yield curve)."""

from __future__ import annotations

from typing import Any

from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable

GLOBAL_9 = ["^GSPC", "^IXIC", "^DJI", "^N225", "^HSI", "000001.SS", "^KS11", "^GDAXI", "^FTSE"]
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
