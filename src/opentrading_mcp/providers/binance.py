"""Binance public REST provider (spot + futures, no API key).

Read-only market data: 24h tickers, funding rates, open interest,
long/short ratios and recent liquidations.
"""

from __future__ import annotations

import json
import re
from typing import Any

from opentrading_mcp.providers.circuit import guarded
from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable

SPOT_BASE = "https://api.binance.com"
SPOT_MIRRORS = [
    "https://api.binance.com",
    "https://data-api.binance.vision",  # public market-data only, no Cloudflare wall
]
FAPI_BASE = "https://fapi.binance.com"
_REQ_TIMEOUT = 10.0


def _norm(symbol: str) -> str:
    """Normalize BTC/USDT, BTC-USDT, btcusdt -> BTCUSDT (raises on garbage)."""
    clean = re.sub(r"[^A-Za-z0-9]", "", symbol or "").upper()
    if not re.fullmatch(r"[A-Z0-9]{6,20}", clean):
        raise ProviderBadData(f"bad crypto symbol {symbol!r}")
    return clean


def _get_json(url: str, params: dict[str, Any]) -> Any:
    try:
        import httpx
    except ImportError as exc:
        raise ProviderUnavailable("httpx not installed") from exc
    try:
        resp = httpx.get(url, params=params, timeout=_REQ_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        raise ProviderUnavailable(f"binance GET failed: {exc}") from exc


def _num(val: Any) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


@guarded("binance")
def spot_board(symbols: list[str]) -> list[dict[str, Any]]:
    """24h tickers for up to 10 normalized symbols.

    Falls back to data-api.binance.vision when api.binance.com 418s (datacenter IPs).
    """
    syms = [_norm(s) for s in symbols if str(s).strip()][:10]
    if not syms:
        raise ProviderBadData("need at least 1 symbol")
    last_exc: Exception | None = None
    for base in SPOT_MIRRORS:
        try:
            data = _get_json(
                f"{base}/api/v3/ticker/24hr", {"symbols": json.dumps(syms, separators=(",", ":"))}
            )
            break
        except Exception as exc:
            last_exc = exc
            continue
    else:
        raise ProviderUnavailable(f"binance spot unreachable (api + vision): {last_exc}")
    rows = data if isinstance(data, list) else [data]
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "symbol": str(row.get("symbol", "")),
                "last": _num(row.get("lastPrice")),
                "change_pct": _num(row.get("priceChangePercent")),
                "high": _num(row.get("highPrice")),
                "low": _num(row.get("lowPrice")),
                "volume": _num(row.get("volume")),
                "quote_volume": _num(row.get("quoteVolume")),
            }
        )
    return out


@guarded("binance")
def derivs_board(symbols: list[str]) -> list[dict[str, Any]]:
    """Funding + OI + account/taker long-short for up to 5 symbols (all public)."""
    syms = [_norm(s) for s in symbols if str(s).strip()][:5]
    if not syms:
        raise ProviderBadData("need at least 1 symbol")
    out: list[dict[str, Any]] = []
    for sym in syms:
        try:
            prem = _get_json(f"{FAPI_BASE}/fapi/v1/premiumIndex", {"symbol": sym})
            oi = _get_json(f"{FAPI_BASE}/fapi/v1/openInterest", {"symbol": sym})
            lsr = _get_json(
                f"{FAPI_BASE}/futures/data/topLongShortAccountRatio",
                {"symbol": sym, "period": "1d", "limit": 1},
            )
            taker = _get_json(
                f"{FAPI_BASE}/futures/data/takerlongshortRatio",
                {"symbol": sym, "period": "1d", "limit": 1},
            )
        except ProviderUnavailable as exc:
            out.append({"symbol": sym, "error": str(exc)})
            continue
        ratio = None
        if isinstance(lsr, list) and lsr:
            ratio = _num(lsr[0].get("longShortRatio") if isinstance(lsr[0], dict) else None)
        taker_ratio = None
        if isinstance(taker, list) and taker:
            taker_ratio = _num(taker[0].get("buySellRatio") if isinstance(taker[0], dict) else None)
        entry: dict[str, Any] = {
            "symbol": sym,
            "mark_price": _num(prem.get("markPrice")) if isinstance(prem, dict) else None,
            "funding_rate": _num(prem.get("lastFundingRate")) if isinstance(prem, dict) else None,
            "next_funding_time": prem.get("nextFundingTime") if isinstance(prem, dict) else None,
            "open_interest": _num(oi.get("openInterest")) if isinstance(oi, dict) else None,
            "ls_ratio": ratio,
            "taker_ls_ratio": taker_ratio,
        }
        out.append(entry)
    return out
