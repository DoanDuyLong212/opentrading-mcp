"""Binance public REST provider (spot + futures, no API key).

Read-only market data: 24h tickers, funding rates, open interest,
long/short ratios and recent liquidations.
"""

from __future__ import annotations

import json
import re
import threading
from typing import Any

import httpx

from opentrading_mcp.providers.circuit import guarded
from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable

SPOT_BASE = "https://api.binance.com"
SPOT_MIRRORS = [
    "https://api.binance.com",
    "https://data-api.binance.vision",  # public market-data only, no Cloudflare wall
]

# CoinGecko ids for common quote pairs (last-resort spot fallback, USD only)
_COINGECKO_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "BNB": "binancecoin",
    "XRP": "ripple", "DOGE": "dogecoin", "ADA": "cardano", "AVAX": "avalanche-2",
    "LINK": "chainlink", "TON": "the-toncoin", "TRX": "tron", "DOT": "polkadot",
    "MATIC": "matic-network", "LTC": "litecoin", "BCH": "bitcoin-cash",
    "NEAR": "near", "UNI": "uniswap", "ATOM": "cosmos", "ETC": "ethereum-classic",
    "FIL": "filecoin", "APT": "aptos", "ARB": "arbitrum", "OP": "optimism",
}
FAPI_BASE = "https://fapi.binance.com"
_REQ_TIMEOUT = 10.0

# One pooled client (keep-alive): derivs_board fires up to 4 calls/symbol and
# one-shot httpx.get() re-paid TLS on every one (~20 handshakes per call).
_client: httpx.Client | None = None
_client_lock = threading.Lock()


def _shared() -> httpx.Client:
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client
        _client = httpx.Client(
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=10),
            timeout=_REQ_TIMEOUT,
        )
        return _client


def _norm(symbol: str) -> str:
    """Normalize BTC/USDT, BTC-USDT, btcusdt -> BTCUSDT (raises on garbage)."""
    clean = re.sub(r"[^A-Za-z0-9]", "", symbol or "").upper()
    if not re.fullmatch(r"[A-Z0-9]{6,20}", clean):
        raise ProviderBadData(f"bad crypto symbol {symbol!r}")
    return clean


def _get_json(url: str, params: dict[str, Any]) -> Any:
    try:
        resp = _shared().get(url, params=params, timeout=_REQ_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        raise ProviderUnavailable(f"binance GET failed: {exc}") from exc


def _num(val: Any) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _coingecko_fallback(syms: list[str], last_exc: Exception | None) -> list[dict[str, Any]]:
    """Last-resort spot prices via CoinGecko (USD only, no high/low)."""
    ids: dict[str, str] = {}
    for s in syms:
        base = re.sub(r"(USDT|USDC|BUSD|USD)$", "", s)
        cid = _COINGECKO_IDS.get(base, base.lower())
        ids[cid] = s
    if not ids:
        raise ProviderUnavailable(f"no coingecko mapping: {last_exc}")
    try:
        data = _get_json(
            "https://api.coingecko.com/api/v3/simple/price",
            {"ids": ",".join(ids), "vs_currencies": "usd",
             "include_24hr_change": "true", "include_24hr_vol": "true"},
        )
    except Exception as exc:
        raise ProviderUnavailable(f"binance + coingecko unreachable: {exc}") from exc
    if not isinstance(data, dict) or not data:
        raise ProviderUnavailable(f"binance + coingecko empty: {last_exc}")
    out = [
        {"symbol": sym, "lastPrice": v.get("usd"),
         "priceChangePercent": v.get("usd_24h_change"),
         "highPrice": None, "lowPrice": None,
         "volume": v.get("usd_24h_vol"), "quoteVolume": None}
        for cid, sym in ids.items()
        if isinstance((v := data.get(cid)), dict) and v.get("usd") is not None
    ]
    if not out:
        raise ProviderUnavailable(f"binance + coingecko empty: {last_exc}")
    return out


@guarded("binance")
def spot_board(symbols: list[str]) -> list[dict[str, Any]]:
    """24h tickers for up to 10 normalized symbols.

    Falls back to data-api.binance.vision when api.binance.com 418s
    (datacenter IPs), then CoinGecko (USD only, no high/low).
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
        data = _coingecko_fallback(syms, last_exc)
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
