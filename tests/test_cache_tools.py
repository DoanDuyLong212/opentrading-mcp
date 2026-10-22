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


def test_price_ttl_switches():
    assert price_ttl(_dt(10, 0, 0)) == TTL_SECONDS["market"]
    assert price_ttl(_dt(20, 0, 0)) == TTL_SECONDS["market_offhours"]  # 13h to the open


def test_price_ttl_never_reaches_past_the_open():
    # 08:59 Monday: one minute to the open, not the 2h off-hours ceiling.
    assert price_ttl(_dt(8, 59, 0)) == 60
    # Friday 15:30 and Saturday noon: next open is Monday 09:00, ceiling applies.
    assert price_ttl(_dt(15, 30, 4)) == TTL_SECONDS["market_offhours"]
    assert price_ttl(_dt(12, 0, 5)) == TTL_SECONDS["market_offhours"]
    # Sunday 08:00: Monday's open is 25h away.
    assert price_ttl(_dt(8, 0, 6)) == TTL_SECONDS["market_offhours"]


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
    # The provider survives the round trip; the reuse is flagged separately.
    assert hit["provenance"]["source"] == "s"
    assert hit["provenance"]["cached"] is True
    assert hit["provenance"]["cached_at"] == env["provenance"]["as_of"]
    assert hit["provenance"]["data_time"] == "2026-10-14"
    assert any("dùng lại bản đã lưu" in w for w in hit["warnings"])


def test_legacy_entry_without_source_reads_as_cache():
    import json

    from opentrading_mcp.providers.store import cache_set
    from opentrading_mcp.tools.shared import _cache_key_for

    key = _run(_cache_key_for("t2old", "fp"))
    cache_set(key, json.dumps({"data": {"a": 1}, "as_of": "2026-10-14T09:00:00+07:00"}), 60)
    hit = _run(cache_lookup("t2old", "fp"))
    assert hit["provenance"]["source"] == "cache"
    assert hit["provenance"]["data_time"] == "2026-10-14T09:00:00+07:00"


def test_partial_results_are_kept_briefly(monkeypatch):
    import opentrading_mcp.tools.shared as shared

    seen: list[int] = []
    monkeypatch.setattr(store_mod, "cache_set", lambda key, value, ttl: seen.append(ttl))
    _run(cache_store("t4", "fp", 900, {"rows": [1]}, source="s", availability="partial"))
    _run(cache_store("t4", "fp2", 900, {"rows": [1]}, source="s"))
    assert seen == [shared._PARTIAL_TTL, 900]


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


def _tool(key: str, fetch, availability: str | None = None):
    """One request the way tools use the helpers: lookup, else fetch and store."""

    async def request():
        hit = await cache_lookup("sf", key)
        if hit is not None:
            return hit
        data = await fetch()
        return await cache_store("sf", key, 60, data, source="live", availability=availability)

    return request


def test_singleflight_coalesces_concurrent_misses(monkeypatch):
    """5 concurrent requests -> 1 upstream fetch, every caller gets its data."""
    import opentrading_mcp.tools.shared as shared

    monkeypatch.setattr(store_mod, "_redis", lambda: None)
    monkeypatch.setattr(shared, "_WAITER_TIMEOUT", 5.0)
    calls = 0

    async def fetch():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.1)
        return {"v": 1}

    async def main():
        request = _tool("k1", fetch)
        envs = await asyncio.gather(*(asyncio.create_task(request()) for _ in range(5)))
        assert calls == 1
        assert all(env["data"] == {"v": 1} for env in envs)
        assert all(env["provenance"]["source"] == "live" for env in envs)

    _run(main())


def test_singleflight_shares_an_empty_result_and_a_retry_does_not_wait(monkeypatch):
    """Empties are not stored, but waiters get them and the next call fetches at once."""
    import opentrading_mcp.tools.shared as shared

    monkeypatch.setattr(store_mod, "_redis", lambda: None)
    monkeypatch.setattr(shared, "_WAITER_TIMEOUT", 5.0)
    calls = 0

    async def fetch():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.1)
        return {}

    async def main():
        request = _tool("k2", fetch, availability="empty")
        envs = await asyncio.gather(*(asyncio.create_task(request()) for _ in range(3)))
        assert calls == 1
        assert all(env["availability"] == "empty" for env in envs)
        started = time.monotonic()
        await asyncio.create_task(request())  # a later retry of the same call
        assert calls == 2
        assert time.monotonic() - started < 1.0

    _run(main())


def test_singleflight_leader_without_store_releases_waiters(monkeypatch):
    """A leader that returns an error envelope (no cache_store) frees waiters when it ends."""
    import opentrading_mcp.tools.shared as shared

    monkeypatch.setattr(store_mod, "_redis", lambda: None)
    monkeypatch.setattr(shared, "_WAITER_TIMEOUT", 5.0)

    async def failing_leader():
        assert await cache_lookup("sf", "k3") is None
        await asyncio.sleep(0.1)
        return "error envelope"  # returns without cache_store

    async def main():
        leader = asyncio.create_task(failing_leader())
        await asyncio.sleep(0.02)
        started = time.monotonic()
        waiter = asyncio.create_task(cache_lookup("sf", "k3"))
        assert await leader == "error envelope"
        assert await waiter is None  # becomes the leader of the retry
        assert time.monotonic() - started < 1.0

    _run(main())


def test_singleflight_same_task_lookup_never_waits_on_itself(monkeypatch):
    import opentrading_mcp.tools.shared as shared

    monkeypatch.setattr(store_mod, "_redis", lambda: None)
    monkeypatch.setattr(shared, "_WAITER_TIMEOUT", 5.0)

    async def main():
        assert await cache_lookup("sf", "k4") is None
        started = time.monotonic()
        assert await cache_lookup("sf", "k4") is None
        assert time.monotonic() - started < 0.5

    _run(main())


def test_singleflight_waiter_times_out_on_a_stuck_leader(monkeypatch):
    """A leader that never finishes must not wedge waiters forever."""
    import opentrading_mcp.tools.shared as shared

    monkeypatch.setattr(store_mod, "_redis", lambda: None)
    monkeypatch.setattr(shared, "_WAITER_TIMEOUT", 0.2)

    async def stuck_leader():
        assert await cache_lookup("sf", "k5") is None
        await asyncio.sleep(10)

    async def main():
        leader = asyncio.create_task(stuck_leader())
        await asyncio.sleep(0.02)
        started = time.monotonic()
        assert await cache_lookup("sf", "k5") is None
        assert time.monotonic() - started >= 0.2
        leader.cancel()

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


def test_neg_cache_is_per_call_and_ignores_fast_failures(monkeypatch):
    """A timeout blocks only that call's arguments; a quick failure blocks nothing."""
    import functools

    import opentrading_mcp.tools.shared as shared

    monkeypatch.setenv("MCP_NEG_TTL", "60")
    shared._neg.clear()

    def quote(symbol: str) -> str:
        if symbol == "SLOW":
            time.sleep(2)
        if symbol == "BAD":
            raise ProviderUnavailable("unknown symbol")
        return symbol

    with pytest.raises(ProviderUnavailable, match="timed out"):
        _run(shared.run_blocking(functools.partial(quote, "SLOW"), "vn_quote_history", 0.1))
    with pytest.raises(ProviderUnavailable, match="briefly unavailable"):
        _run(shared.run_blocking(functools.partial(quote, "SLOW"), "vn_quote_history", 5.0))
    # Another symbol on the same tool still runs.
    assert _run(shared.run_blocking(functools.partial(quote, "FPT"), "vn_quote_history")) == "FPT"
    # A fast ProviderUnavailable is not remembered.
    for _ in range(2):
        with pytest.raises(ProviderUnavailable, match="unknown symbol"):
            _run(shared.run_blocking(functools.partial(quote, "BAD"), "vn_quote_history"))
    shared._neg.clear()
