"""Unit tests for the read-through cache helpers (offline-safe, no network).

Covers: session-hour detection, price TTL switching, fingerprint hashing,
never-cache-failures rule, memory-fallback bound, and last-bar extraction.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from opentrading_mcp.cache import TTL_SECONDS
from opentrading_mcp.providers import store as store_mod
from opentrading_mcp.providers.errors import ProviderUnavailable
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


def test_singleflight_coalesces_concurrent_misses(monkeypatch):
    """5 concurrent missers -> 1 leader fetches, waiters share the store."""
    import opentrading_mcp.tools.shared as shared

    monkeypatch.setattr(store_mod, "_redis", lambda: None)
    monkeypatch.setattr(shared, "_WAITER_TIMEOUT", 5.0)
    _memory.clear()

    async def main():
        leader = asyncio.create_task(cache_lookup("sf", "k1"))
        await asyncio.sleep(0.05)  # let the leader register first
        waiters = [asyncio.create_task(cache_lookup("sf", "k1")) for _ in range(4)]
        await asyncio.sleep(0.05)
        assert await leader is None  # leader fetches upstream
        stored = await cache_store("sf", "k1", 60, {"v": 1}, source="live")
        assert stored["data"] == {"v": 1}
        for env in await asyncio.gather(*waiters):
            assert env["data"] == {"v": 1}
            assert any("cache lúc" in w for w in env["warnings"])

    _run(main())


def test_singleflight_waiter_times_out_when_leader_dies(monkeypatch):
    """A leader that never stores must not wedge waiters forever."""
    import opentrading_mcp.tools.shared as shared

    monkeypatch.setattr(store_mod, "_redis", lambda: None)
    monkeypatch.setattr(shared, "_WAITER_TIMEOUT", 0.2)
    _memory.clear()

    async def main():
        assert await cache_lookup("sf", "k2") is None  # leader
        started = time.monotonic()
        assert await cache_lookup("sf", "k2") is None  # waiter times out
        assert time.monotonic() - started >= 0.2

    _run(main())


def test_run_blocking_sheds_when_queue_full(monkeypatch):
    """Past MCP_QUEUE_SHED outstanding calls, fail fast instead of queueing."""
    import opentrading_mcp.tools.shared as shared

    monkeypatch.setattr(store_mod, "_redis", lambda: None)
    monkeypatch.setenv("MCP_QUEUE_SHED", "1")

    async def main():
        bg = asyncio.create_task(
            shared.run_blocking(lambda: time.sleep(0.4) or "done", "bg", 5.0)
        )
        await asyncio.sleep(0.05)
        with pytest.raises(ProviderUnavailable, match="shed"):
            await shared.run_blocking(lambda: 1, "x", 5.0)
        assert await bg == "done"
        assert shared._pending == 0

    _run(main())


def test_run_blocking_heavy_pool():
    import opentrading_mcp.tools.shared as shared

    assert _run(shared.run_blocking(lambda: 42, "h", heavy=True)) == 42


def test_neg_cache_fails_fast_after_timeout(monkeypatch):
    """A timed-out leg is remembered briefly; auth-missing never is."""
    import opentrading_mcp.tools.shared as shared
    from opentrading_mcp.providers.errors import ProviderAuthMissing

    monkeypatch.setenv("MCP_NEG_TTL", "60")
    shared._neg.clear()

    async def slow() -> None:
        await shared.run_blocking(lambda: time.sleep(2), "negtool", 0.1)

    with pytest.raises(ProviderUnavailable, match="timed out"):
        _run(slow())
    started = time.monotonic()
    with pytest.raises(ProviderUnavailable, match="briefly unavailable"):
        _run(shared.run_blocking(lambda: 1, "negtool", 5.0))
    assert time.monotonic() - started < 1.0  # fast, no 5s wait

    async def auth_fail() -> None:
        def _raise() -> None:
            raise ProviderAuthMissing("no key")

        await shared.run_blocking(_raise, "negtool2", 5.0)

    with pytest.raises(ProviderAuthMissing):
        _run(auth_fail())
    # auth-missing is NOT remembered: a second call still runs the fn
    def _raise_again() -> None:
        raise ProviderAuthMissing("x")

    with pytest.raises(ProviderAuthMissing):
        _run(shared.run_blocking(_raise_again, "negtool2", 5.0))
    assert shared._neg.get("negtool2") is None
    shared._neg.clear()
