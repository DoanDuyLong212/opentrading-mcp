"""Tiered cache: Redis when reachable, process-memory fallback otherwise.

Keys follow cache.cache_key so web + worker share the namespace.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from typing import Any

_memory: dict[str, tuple[float, str]] = {}

# One client (with its connection pool) per process. A new client per call meant a new
# TLS handshake plus a PING for every cache read, and handlers call this from the event
# loop. After a failure Redis is skipped for _RETRY_AFTER seconds instead of being retried
# (and timing out) on every call.
_RETRY_AFTER = 30.0
_client: Any = None
_client_url: str | None = None
_down_until = 0.0
_client_lock = threading.Lock()


def _redis() -> Any:
    global _client, _client_url, _down_until
    url = os.environ.get("REDIS_URL")
    if not url:
        return None
    if _client is not None and _client_url == url:
        return _client
    if time.monotonic() < _down_until:
        return None
    with _client_lock:
        if _client is not None and _client_url == url:
            return _client
        try:
            import redis

            client = redis.Redis.from_url(
                url, socket_connect_timeout=2, socket_timeout=3, health_check_interval=30
            )
            client.ping()
        except Exception:
            _down_until = time.monotonic() + _RETRY_AFTER
            return None
        _client, _client_url = client, url
        return client


def _redis_failed() -> None:
    """A command on the shared client failed: drop it and back off."""
    global _client, _down_until
    _client = None
    _down_until = time.monotonic() + _RETRY_AFTER


def cache_get(key: str) -> str | None:
    client = _redis()
    if client is not None:
        try:
            value = client.get(key)
            return value.decode() if isinstance(value, bytes) else value
        except Exception:
            _redis_failed()
    hit = _memory.get(key)
    if hit is None:
        return None
    expires_at, value = hit
    if time.time() > expires_at:
        _memory.pop(key, None)
        return None
    return value


def cache_set(key: str, value: str | dict[str, Any], ttl_seconds: int) -> None:
    payload = value if isinstance(value, str) else json.dumps(value, default=str)
    client = _redis()
    if client is not None:
        try:
            client.setex(key, ttl_seconds, payload)
        except Exception:
            _redis_failed()
    _memory[key] = (time.time() + ttl_seconds, payload)


async def acache_get(key: str) -> str | None:
    """cache_get for async handlers: Redis I/O must not block the event loop."""
    return await asyncio.to_thread(cache_get, key)


async def acache_set(key: str, value: str | dict[str, Any], ttl_seconds: int) -> None:
    await asyncio.to_thread(cache_set, key, value, ttl_seconds)
