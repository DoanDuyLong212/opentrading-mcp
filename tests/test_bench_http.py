"""Benchmark regression checks: envelope failures, timer and distinct scenarios."""
from __future__ import annotations

import json

import httpx
import pytest
from scripts import load_bench_http as bench


def _rpc(availability="available", error=None):
    env = {"data": {"rsi14": 55.}, "availability": availability,
           "provenance": {"cached": False}}
    if error:
        env["error"] = error
    return {"jsonrpc": "2.0", "id": 1, "result": {"isError": False,
        "content": [{"type": "text", "text": json.dumps(env)}]}}


@pytest.mark.parametrize("availability", ["unavailable", "empty", "partial", "failed"])
def test_application_failure_is_not_success(availability):
    assert bench._sse_result("data: " + json.dumps(_rpc(availability))) == (True, False)


def test_notifications_do_not_hide_response():
    text = 'data: {"jsonrpc":"2.0","method":"notifications/progress"}\n\n'
    text += "data: " + json.dumps(_rpc()) + "\n\n"
    assert bench._sse_result(text) == (True, True)
    assert bench._sse_result("data: " + json.dumps(_rpc(error={"code": "bad"}))) == (True, False)
    assert bench._sse_result('data: {"jsonrpc":"2.0","id":1}') == (False, False)


@pytest.fixture
def fake_server(monkeypatch):
    import asyncio

    real_client = httpx.AsyncClient
    configurations = []

    async def handle(request):
        if request.url.path == "/__bench/config":
            config = json.loads(request.content)
            configurations.append(config)
            return httpx.Response(200, json=config)
        if request.url.path == "/__bench/state":
            return httpx.Response(200, json={"pending": 0, "active": 0,
                                            "redis_client_active": True})
        await asyncio.sleep(.005)
        body = _rpc()
        args = json.loads(request.content)["params"]["arguments"]
        if "peers" in args:
            env = {"data": {"rows": [{"roe": .15}] * 6}, "availability": "available"}
            body["result"]["structuredContent"] = env
        return httpx.Response(200, text="data: " + json.dumps(body))

    monkeypatch.setattr(bench.httpx, "AsyncClient", lambda **kwargs:
                        real_client(transport=httpx.MockTransport(handle), **kwargs))
    return configurations


@pytest.mark.asyncio
async def test_sample_timer_excludes_warmup_and_namespaces_are_unique(fake_server):
    rows = [await bench.run_scenario("http://test", 1, mode="cold",
              warmup_seconds=.05, sample_seconds=.03) for _ in range(2)]
    for row in rows:
        assert .03 <= row["sample_seconds"] < .07
        assert row["rps"] == round(row["requests"] / row["sample_seconds"], 2)
    symbols = [{r["symbol"] for r in row["raw_requests"]} for row in rows]
    assert not symbols[0] & symbols[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["stall", "health-under-load", "peer", "burst"])
async def test_scenarios_execute_and_recover(fake_server, mode):
    row = await bench.run_scenario("http://test", 2, mode=mode,
                                  warmup_seconds=0, sample_seconds=.03)
    assert row["requests"] >= 2
    assert row["success_rate"] == 100
    assert row["recovery_ok"]
    if mode == "stall":
        assert fake_server[0]["latency_ms"] == 1000
    if mode == "health-under-load":
        assert row["health_probes"] and all(r["ok"] for r in row["health_probes"])


@pytest.mark.asyncio
async def test_redis_down_stops_and_restarts_disposable_container(fake_server, monkeypatch):
    actions = []

    async def check(container):
        assert container == "disposable"

    async def docker(action, container):
        actions.append(action)

    monkeypatch.setattr(bench, "_check_disposable", check)
    monkeypatch.setattr(bench, "_docker", docker)
    row = await bench.run_scenario("http://test", 2, mode="redis-down",
        warmup_seconds=0, sample_seconds=.03, redis_container="disposable")
    assert actions == ["stop", "start"]
    assert row["outage"]["stopped_during_sample"] and row["recovery_ok"]
