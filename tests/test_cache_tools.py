"""Unit tests for the read-through cache helpers (offline-safe, no network).

Covers: session-hour detection, price TTL switching, fingerprint hashing,
never-cache-failures rule, memory-fallback bound, and last-bar extraction.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from opentrading_mcp.cache import TTL_SECONDS
from opentrading_mcp.providers import store as store_mod
from opentrading_mcp.providers.store import _memory, _memory_store
from opentrading_mcp.tools.shared import (
    cache_lookup,
    cache_store,
    in_vn_session,
    last_bar_time,
    price_ttl,
)


def _dt(hour: int, minute: int = 0, weekday: int = 0) -> datetime:
    # 2026-10-12 is a Monday; shift to the requested weekday at 09:00 ICT.
    base = datetime(2026, 10, 12 + weekday, hour, minute, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    assert base.weekday() == weekday
    return base


def _run(coro):
    return asyncio.run(coro)


def test_in_vn_session_boundaries():
    assert in_vn_session(_dt(9, 0, 0)) is True
    assert in_vn_session(_dt(14, 59, 0)) is True
    assert in_vn_session(_dt(15, 0, 0)) is False
    assert in_vn_session(_dt(8, 59, 4)) is False
    # Saturday
    assert in_vn_session(_dt(10, 0, 5)) is False


def test_price_ttl_switches(monkeypatch):
    import opentrading_mcp.tools.shared as shared

    monkeypatch.setattr(shared, "in_vn_session", lambda: True)
    assert price_ttl() == TTL_SECONDS["market"]
    monkeypatch.setattr(shared, "in_vn_session", lambda: False)
    assert price_ttl() == TTL_SECONDS["market_offhours"]


def test_cache_store_skips_failures_and_empties():
    _memory.clear()
    env = _run(
        cache_store("t1", "fp", 60, {"tool": "t1"}, source="unavailable",
                    warnings=["x"], availability="unavailable")
    )
    assert env["availability"] == "unavailable"
    assert _run(cache_lookup("t1", "fp")) is None
    env = _run(cache_store("t1b", "fp", 60, {}, source="x", availability="empty"))
    assert _run(cache_lookup("t1b", "fp")) is None


def test_cache_roundtrip_with_data_time():
    _memory.clear()
    env = _run(
        cache_store("t2", "fp", 60, {"a": 1}, source="s",
                    data_time="2026-10-14")
    )
    assert env["provenance"]["source"] == "s"
    assert env["provenance"]["data_time"] == "2026-10-14"
    hit = _run(cache_lookup("t2", "fp"))
    assert hit is not None
    assert hit["provenance"]["source"] == "cache"
    assert hit["provenance"]["data_time"] == "2026-10-14"
    assert any("cache lúc" in w for w in hit["warnings"])


def test_long_fingerprint_hashes_no_collision():
    _memory.clear()
    fp_a = "x" * 200 + "A"
    fp_b = "x" * 200 + "B"
    _run(cache_store("t3", fp_a, 60, {"v": "a"}, source="s"))
    _run(cache_store("t3", fp_b, 60, {"v": "b"}, source="s"))
    assert _run(cache_lookup("t3", fp_a))["data"] == {"v": "a"}
    assert _run(cache_lookup("t3", fp_b))["data"] == {"v": "b"}


def test_memory_bound_evicts_oldest():
    _memory.clear()
    for i in range(store_mod._MEMORY_MAX_KEYS + 50):
        _memory_store(f"k{i}", time.time() + 3600, "v")
    assert len(_memory) <= store_mod._MEMORY_MAX_KEYS
    assert "k0" not in _memory  # oldest evicted first


def test_last_bar_time():
    assert last_bar_time([{"t": "2026-10-01"}, {"t": "2026-10-14"}]) == "2026-10-14"
    assert last_bar_time([{"time": "2026-01-01"}]) == "2026-01-01"
    assert last_bar_time([]) is None
    assert last_bar_time([{"c": 1}]) is None
    assert last_bar_time(["nope"]) is None
