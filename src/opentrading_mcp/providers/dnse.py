"""DNSE provider (REST direct; WS snapshot served by worker via Redis)."""

from __future__ import annotations

import os
from typing import Any

import httpx

from opentrading_mcp.providers.errors import (
    ProviderAuthMissing,
    ProviderBadData,
    ProviderUnavailable,
)

BASE = "https://openapi.dnse.com.vn"
API_VERSION = "2026-05-07"


def _headers() -> dict[str, str]:
    key = os.environ.get("DNSE_API_KEY")
    if not key:
        raise ProviderAuthMissing("DNSE_API_KEY is not set")
    return {"Authorization": f"Bearer {key}", "API-Version": API_VERSION}


def ohlc_history(
    symbol: str = "VN30F1M",
    bar_type: str = "derivative",
    resolution: int = 15,
    from_date: str = "2018-08-01",
    page_size: int = 10000,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "type": bar_type,
        "symbol": symbol,
        "resolution": resolution,
        "from": from_date,
        "pageSize": page_size,
    }
    try:
        response = httpx.get(f"{BASE}/price/ohlc", headers=_headers(), params=params, timeout=20)
    except httpx.TimeoutException as exc:
        raise ProviderUnavailable("dnse ohlc timeout") from exc
    except httpx.HTTPError as exc:
        raise ProviderUnavailable("dnse ohlc unreachable") from exc
    if response.status_code == 401:
        raise ProviderAuthMissing("dnse rejected api key")
    try:
        body = response.json()
    except ValueError as exc:
        raise ProviderBadData("dnse ohlc bad json") from exc
    rows = body.get("data") or body.get("ohlc") or []
    return [
        {
            "t": r.get("t"),
            "o": r.get("o"),
            "h": r.get("h"),
            "l": r.get("l"),
            "c": r.get("c"),
            "v": r.get("v"),
        }
        for r in rows
    ]


def latest_trade(symbols: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        for symbol in symbols:
            response = httpx.get(
                f"{BASE}/price/{symbol}/trades/latest", headers=_headers(), timeout=10
            )
            if response.status_code == 200:
                out.append({"symbol": symbol, **response.json()})
    except ProviderAuthMissing:
        raise
    except httpx.HTTPError as exc:
        raise ProviderUnavailable("dnse latest trade unreachable") from exc
    return out


def ws_snapshot(symbols: list[str]) -> dict[str, Any]:
    from opentrading_mcp.providers.store import cache_get

    data: dict[str, Any] = {}
    for symbol in symbols:
        hit = cache_get(f"mcp:market:dnse_ws_snapshot:{symbol}")
        if hit is not None:
            import json

            data[symbol] = json.loads(hit)
    if not data:
        raise ProviderUnavailable("ws worker has not published yet")
    return data
