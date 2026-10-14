"""Test isolation: the process-memory cache tier must not leak between tests.

Each test gets a fresh memory cache so a cached success from one test can
never mask another test's live fetch, auth-missing failure, or source
assertion. (Production Redis is untouched — tests run without REDIS_URL.)
"""

from __future__ import annotations

import pytest

from opentrading_mcp.providers.store import _memory


@pytest.fixture(autouse=True)
def _isolate_memory_cache():
    _memory.clear()
    yield
    _memory.clear()
