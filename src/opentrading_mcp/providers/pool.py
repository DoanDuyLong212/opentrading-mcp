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
_insecure: httpx.Client | None = None
_lock = threading.Lock()


def shared_client() -> httpx.Client:
    """Process-wide keep-alive client (10 conns, 20s default timeout).

    Per-request ``timeout=``/``headers=``/``follow_redirects=`` apply; TLS
    verification is fixed per client (httpx has no per-request ``verify``),
    so unverified fallbacks use ``insecure_client()``. Redirects are followed
    and cookies persist: only for fixed provider hosts, never arbitrary URLs
    (webfetch builds its own client).
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


def insecure_client() -> httpx.Client:
    """Keep-alive client with TLS verification off, for hosts with broken chains.

    Callers must report the response as unverified (vn_public's tls flag).
    """
    global _insecure
    if _insecure is not None:
        return _insecure
    with _lock:
        if _insecure is not None:
            return _insecure
        _insecure = httpx.Client(
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=4),
            timeout=20.0,
            follow_redirects=True,
            verify=False,
        )
        return _insecure


def get(url: str, **kwargs: Any) -> httpx.Response:
    """Drop-in for httpx.get over the shared pool."""
    return shared_client().get(url, **kwargs)


def post(url: str, **kwargs: Any) -> httpx.Response:
    """Drop-in for httpx.post over the shared pool."""
    return shared_client().post(url, **kwargs)
