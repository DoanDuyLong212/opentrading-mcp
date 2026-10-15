"""Test isolation: the process-memory cache tier must not leak between tests.

Each test gets a fresh memory cache so a cached success from one test can
never mask another test's live fetch, auth-missing failure, or source
assertion. (Production Redis is untouched — tests run without REDIS_URL.)
Single-flight and negative-cache registries are cleared for the same reason.
"""

from __future__ import annotations

import pytest

from opentrading_mcp.providers.store import _memory


@pytest.fixture(autouse=True)
def _isolate_memory_cache():
    _memory.clear()
    try:
        from opentrading_mcp.tools import shared as _shared

        _shared._neg.clear()
        with _shared._inflight_guard:
            _shared._inflight.clear()
    except Exception:
        pass
    yield
    _memory.clear()
