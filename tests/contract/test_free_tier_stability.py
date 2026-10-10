"""Contract: the server stays responsive on a 0.1-CPU host (Render free, incident 10/10/2026).

Five concurrent cold tool calls starved the event loop, /healthz stopped answering
within Render's 5s and the instance was killed with every call in flight.
"""

from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from starlette.testclient import TestClient

from opentrading_mcp.providers.errors import ProviderUnavailable
from opentrading_mcp.server import create_server, register_all


def _server() -> Any:
    from opentrading_mcp.cli import add_health_routes

    server = create_server()
    register_all(server)
    add_health_routes(server)
    return server


def test_healthz_is_liveness_only(monkeypatch):
    from opentrading_mcp import health

    calls: list[bool] = []

    async def report(deep: bool = False) -> tuple[int, dict[str, Any]]:
        calls.append(deep)
        return 503, {"ok": False}

    monkeypatch.setattr(health, "health_report", report)
    client = TestClient(_server().streamable_http_app())
    resp = client.get("/healthz")
    assert resp.status_code == 200 and resp.json()["ok"] is True
    assert calls == [], "/healthz must not touch Redis/Postgres"
    # Dependency checks moved to /readyz (and stay reachable as ?full=1 / ?deep=1).
    assert client.get("/readyz").status_code == 503
    assert client.get("/healthz?full=1").status_code == 503
    assert client.get("/healthz?deep=1").status_code == 503
    assert calls == [False, False, True]


@pytest.fixture
def one_slot(monkeypatch):
    from opentrading_mcp.tools import shared

    pool = ThreadPoolExecutor(max_workers=1)
    monkeypatch.setattr(shared, "_EXECUTOR", pool)
    yield shared
    pool.shutdown(wait=False)


def test_slot_stays_taken_until_a_timed_out_call_really_ends(one_slot):
    async def scenario() -> None:
        with pytest.raises(ProviderUnavailable):
            await one_slot.run_blocking(lambda: time.sleep(0.6), "slow", timeout_secs=0.1)
        # The thread above still runs: a new call must not start next to it.
        ran: list[bool] = []
        with pytest.raises(ProviderUnavailable):
            await one_slot.run_blocking(lambda: ran.append(True), "queued", timeout_secs=0.2)
        await asyncio.sleep(0.7)
        assert ran == [], "a call whose time ran out while queued must not run later"
        assert await one_slot.run_blocking(lambda: 42, "after", timeout_secs=1.0) == 42

    asyncio.run(scenario())


def test_blocking_calls_are_capped(monkeypatch):
    from opentrading_mcp.tools import shared

    monkeypatch.setattr(shared, "_EXECUTOR", ThreadPoolExecutor(max_workers=2))
    running = 0
    peak = 0
    lock = threading.Lock()

    def work() -> int:
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        time.sleep(0.1)
        with lock:
            running -= 1
        return 1

    async def scenario() -> list[int]:
        return await asyncio.gather(*(shared.run_blocking(work, "w", 5.0) for _ in range(6)))

    assert sum(asyncio.run(scenario())) == 6
    assert peak == 2


def test_market_snapshot_keeps_redis_off_the_event_loop(monkeypatch):
    import opentrading_mcp.providers.store as store
    import opentrading_mcp.providers.vnstock as vn_p

    def slow_get(_key: str) -> None:
        time.sleep(0.5)  # a Redis round trip that hangs

    import opentrading_mcp.tools.market as market

    monkeypatch.setattr(store, "cache_get", slow_get)
    monkeypatch.setattr(store, "cache_set", lambda *a, **k: None)
    # Older code imported these names into the tool module and called them on the loop.
    monkeypatch.setattr(market, "cache_get", slow_get, raising=False)
    monkeypatch.setattr(market, "cache_set", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(vn_p, "equity_quote_batch", lambda symbols: [{"symbol": "VCB"}])
    fn = _server()._tool_manager.get_tool("market_snapshot").fn

    async def scenario() -> float:
        lag = 0.0

        async def ticker() -> None:
            nonlocal lag
            for _ in range(30):
                started = time.monotonic()
                await asyncio.sleep(0.02)
                lag = max(lag, time.monotonic() - started - 0.02)

        async def call() -> None:
            await asyncio.sleep(0.05)  # the ticker is already measuring
            await fn(symbols=["VCB"])

        await asyncio.gather(ticker(), call())
        return lag

    assert asyncio.run(scenario()) < 0.2


def test_symbol_list_is_fetched_once_for_concurrent_cold_calls(monkeypatch):
    import opentrading_mcp.providers.vnstock as vn_p

    fetches = 0

    def fetch() -> list[dict[str, str]]:
        nonlocal fetches
        fetches += 1
        time.sleep(0.2)
        return [{"symbol": "VCB", "name": "Vietcombank"}, {"symbol": "FPT", "name": "FPT"}]

    monkeypatch.setattr(vn_p, "_listing", None)
    monkeypatch.setattr(vn_p, "_listing_failed_until", 0.0)
    monkeypatch.setattr(vn_p, "_fetch_listing", fetch)
    results: list[list[dict[str, str]]] = []
    def call() -> None:
        results.append(vn_p.listing_symbols())

    threads = [threading.Thread(target=call) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert fetches == 1
    assert all(len(r) == 2 for r in results)
    assert vn_p.listing_symbols(limit=1) == [{"symbol": "VCB", "name": "Vietcombank"}]
    assert fetches == 1


def test_a_failed_symbol_list_fetch_is_not_repeated_by_every_waiter(monkeypatch):
    import opentrading_mcp.providers.vnstock as vn_p

    fetches = 0

    def fetch() -> list[dict[str, str]]:
        nonlocal fetches
        fetches += 1
        raise ProviderUnavailable("vnstock listing failed")

    monkeypatch.setattr(vn_p, "_listing", None)
    monkeypatch.setattr(vn_p, "_listing_failed_until", 0.0)
    monkeypatch.setattr(vn_p, "_fetch_listing", fetch)
    for _ in range(3):
        with pytest.raises(ProviderUnavailable):
            vn_p.listing_symbols()
    assert fetches == 1


def test_unreachable_redis_is_skipped_for_a_while(monkeypatch):
    import redis

    import opentrading_mcp.providers.store as store

    attempts = 0

    def from_url(*_a: Any, **_k: Any) -> Any:
        nonlocal attempts
        attempts += 1
        raise redis.ConnectionError("down")

    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1")
    monkeypatch.setattr(store, "_client", None)
    monkeypatch.setattr(store, "_down_until", 0.0)
    monkeypatch.setattr(redis.Redis, "from_url", from_url)
    monkeypatch.setattr(store, "_memory", {})
    store.cache_set("k", "v", 60)
    assert store.cache_get("k") == "v"  # memory fallback still works
    assert attempts == 1, "a down Redis must not be retried on every call"


def test_a_library_calling_sys_exit_in_a_worker_does_not_stop_the_server(one_slot):
    """vnai exits the process when vnstock's 60/min quota is hit; that must stay a tool error."""

    def quota_hit() -> None:
        raise SystemExit("Rate limit exceeded. Process terminated.")

    async def scenario() -> str:
        with pytest.raises(ProviderUnavailable, match="rate limit"):
            await one_slot.run_blocking(quota_hit, "vn_quote_history", timeout_secs=5.0)
        return await one_slot.run_blocking(lambda: "still serving", "next", timeout_secs=5.0)

    assert asyncio.run(scenario()) == "still serving"


def test_source_status_survives_a_quota_exit_in_quota_info(monkeypatch):
    """quota_info runs in a thread outside run_blocking; vnai's sys.exit must not escape it."""
    import opentrading_mcp.providers.vnstock as vn_p

    def exits() -> dict:
        raise SystemExit("Rate limit exceeded. Process terminated.")

    monkeypatch.setattr(vn_p, "quota_info", exits)
    monkeypatch.setattr(vn_p, "quote_history", lambda *a, **k: [])
    fn = _server()._tool_manager.get_tool("source_status").fn
    out = asyncio.run(fn())
    assert "rate limit" in out["data"]["upstreams"]["vnstock_quota"]["error"]
