"""Shared pooled httpx client for low/medium-volume fetchers.

One-shot httpx.get() re-pays TCP+TLS on every call. Modules that fetch
infrequently (DNSE REST, VN public scrapes, webfetch, websearch, geo,
JWKS) share this single keep-alive client instead of growing their own
pools. High-volume modules with their own tuning (intel, binance,
vietstock session) keep dedicated clients.
"""

from __future__ import annotations

import threading
from typing import Any

import httpx

_client: httpx.Client | None = None
_lock = threading.Lock()


def shared_client() -> httpx.Client:
    """Process-wide keep-alive client (10 conns, 20s default timeout).

    Per-request ``timeout=`` / ``verify=`` overrides still apply — pooling
    only reuses the TCP/TLS layer, it does not pin request options.
    """
    global _client
    if _client is not None:
        return _client
    with _lock:
        if _client is not None:
            return _client
        _client = httpx.Client(
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=10),
            timeout=20.0,
            follow_redirects=True,
        )
        return _client


def get(url: str, **kwargs: Any) -> httpx.Response:
    """Drop-in for httpx.get over the shared pool."""
    return shared_client().get(url, **kwargs)


def post(url: str, **kwargs: Any) -> httpx.Response:
    """Drop-in for httpx.post over the shared pool."""
    return shared_client().post(url, **kwargs)
