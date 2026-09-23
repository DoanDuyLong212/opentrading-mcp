"""Tiered cache: Redis when reachable, process-memory fallback otherwise.

Keys follow cache.cache_key so web + worker share the namespace.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

_memory: dict[str, tuple[float, str]] = {}


def _redis() -> Any:
    url = os.environ.get("REDIS_URL")
    if not url:
        return None
    try:
        import redis

        client = redis.Redis.from_url(url, socket_connect_timeout=2, socket_timeout=3)
        client.ping()
        return client
    except Exception:
        return None


def cache_get(key: str) -> str | None:
    client = _redis()
    if client is not None:
        try:
            value = client.get(key)
            return value.decode() if isinstance(value, bytes) else value
        except Exception:
            pass
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
            pass
    _memory[key] = (time.time() + ttl_seconds, payload)
