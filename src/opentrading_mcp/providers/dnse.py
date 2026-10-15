"""DNSE provider: signed REST (HTTPS-signature port, stdlib only) + WS snapshot reader.

REST signing mirrors the official DNSE SDK / Trading_Agents usage:
  Date: <rfc1123 GMT>
  X-Signature: Signature keyId="<key>",algorithm="hmac-sha256",
               headers="(request-target) date",signature="<base64url-quoted>",
               nonce="<hex>"
  x-api-key: <key>
  version: 2026-05-07
Signature string: "(request-target): get <path>\\ndate: <date>[\\nnonce: <nonce>]".
HMAC-SHA256 over it with the API secret, base64, URL-quote.

WS live snapshots are written by the worker (loops.dnse_ws_loop); the tools
here only read the shared Redis keys, so web + worker stay decoupled.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import UTC, datetime
from typing import Any
from urllib import parse
from uuid import uuid4

import httpx

from opentrading_mcp.providers.circuit import guarded
from opentrading_mcp.providers.errors import (
    ProviderAuthMissing,
    ProviderBadData,
    ProviderUnavailable,
)
from opentrading_mcp.providers.pool import shared_client

BASE = "https://openapi.dnse.com.vn"
WS_URL = "wss://ws-openapi.dnse.com.vn/v1/stream?encoding=json"
API_VERSION = "2026-05-07"


def _creds() -> tuple[str, str]:
    key = os.environ.get("DNSE_API_KEY", "").strip()
    secret = os.environ.get("DNSE_SECRET", "").strip()
    if not key or not secret:
        raise ProviderAuthMissing("DNSE_API_KEY/DNSE_SECRET are not set")
    return key, secret


def build_signature(
    secret: str, method: str, path: str, date_value: str, nonce: str | None = None
) -> tuple[str, str]:
    headers = "(request-target) date"
    text = f"(request-target): {method.lower()} {path}\ndate: {date_value}"
    if nonce:
        text += f"\nnonce: {nonce}"
    mac = hmac.new(secret.encode(), text.encode(), hashlib.sha256)
    return headers, parse.quote(base64.b64encode(mac.digest()).decode(), safe="")


def signed_headers(method: str, path: str) -> dict[str, str]:
    key, secret = _creds()
    date_value = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S %z")
    nonce = uuid4().hex
    _, signature = build_signature(secret, method, path, date_value, nonce)
    return {
        "Date": date_value,
        "X-Signature": (
            f'Signature keyId="{key}",algorithm="hmac-sha256",'
            f'headers="(request-target) date",signature="{signature}",nonce="{nonce}"'
        ),
        "x-api-key": key,
        "version": API_VERSION,
    }


@guarded("dnse")
def _get(path: str, params: dict[str, Any] | None = None, timeout: int = 20) -> Any:
    try:
        headers = signed_headers("get", path)
    except ProviderAuthMissing:
        raise
    try:
        response = shared_client().get(
            f"{BASE}{path}", headers=headers, params=params, timeout=timeout
        )
    except httpx.TimeoutException as exc:
        raise ProviderUnavailable(f"dnse timeout: {path}") from exc
    except httpx.HTTPError as exc:
        raise ProviderUnavailable(f"dnse unreachable: {path}") from exc
    if response.status_code == 401:
        raise ProviderAuthMissing("dnse rejected api key")
    try:
        return response.json()
    except ValueError as exc:
        raise ProviderBadData(f"dnse bad json: {path}") from exc


def ohlc_history(
    symbol: str = "VN30F1M",
    bar_type: str = "derivative",
    resolution: int = 15,
    from_date: str = "2018-08-01",
    page_size: int = 10000,
    to_date: str | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "type": bar_type,
        "symbol": symbol,
        "resolution": resolution,
        "from": from_date,
        "pageSize": page_size,
    }
    if to_date:
        params["to"] = to_date
    body = _get("/price/ohlc", params)
    if isinstance(body, dict) and isinstance(body.get("t"), list):
        keys = ("t", "o", "h", "l", "c", "v")
        cols = [body.get(k, []) for k in keys]
        width = min(len(c) for c in cols)
        return [{k: cols[i][n] for i, k in enumerate(keys)} for n in range(width)]
    rows = body.get("data") or body.get("ohlc") or []
    if isinstance(rows, list):
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
            if isinstance(r, dict)
        ]
    return []


def latest_trade(symbols: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for symbol in symbols:
        body = _get(f"/price/{symbol}/trades/latest")
        if isinstance(body, dict):
            out.append({"symbol": symbol, **body})
    return out


def orderbook(symbol: str, depth: int = 3) -> dict[str, Any]:
    for path in (f"/price/{symbol}/quotes/latest", f"/price/{symbol}/quotes"):
        try:
            body = _get(path)
        except (ProviderUnavailable, ProviderBadData):
            continue
        if isinstance(body, dict) and body:
            bids = body.get("bids") or body.get("bid") or []
            asks = body.get("asks") or body.get("ask") or []
            return {"symbol": symbol, "bids": bids[:depth], "asks": asks[:depth]}
    raise ProviderUnavailable(f"no orderbook for {symbol}")


def _coerce_foreign(body: Any) -> Any:
    """Reject DNSE errorCode payloads (e.g. range limits on foreign-trading)."""
    if isinstance(body, dict) and "errorCode" in body:
        code = body.get("errorCode")
        msg = body.get("message")
        raise ProviderBadData(f"dnse foreign-trading error {code}: {msg}")
    return body


def foreign_rest(symbol: str) -> dict[str, Any]:
    body = _get(f"/price/{symbol}/foreign-trading")
    if not body:
        raise ProviderUnavailable(f"no foreign data for {symbol}")
    return {"symbol": symbol, "foreign": _coerce_foreign(body)}


def working_dates() -> Any:
    return _get("/market/working-dates")


def ws_snapshot(symbols: list[str]) -> dict[str, Any]:
    from opentrading_mcp.providers.store import cache_get

    data: dict[str, Any] = {}
    for symbol in symbols:
        hit = cache_get(f"mcp:market:dnse_ws_snapshot:{symbol}")
        if hit is not None:
            data[symbol] = json.loads(hit)
    if not data:
        raise ProviderUnavailable("ws worker has not published yet")
    return data


def build_ws_auth(api_key: str, api_secret: str, timestamp: int, nonce: str) -> dict[str, Any]:
    message = f"{api_key}:{timestamp}:{nonce}"
    signature = hmac.new(api_secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return {
        "action": "auth",
        "api_key": api_key,
        "signature": signature,
        "timestamp": timestamp,
        "nonce": nonce,
    }


def build_ws_subscribe(channel: str, symbols: list[str]) -> dict[str, Any]:
    return {"action": "subscribe", "channels": [{"name": channel, "symbols": symbols}]}
