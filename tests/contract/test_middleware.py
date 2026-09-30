"""Rate limiting (Phase 0) + auth (Phase 2) middleware contract tests."""

import json

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from opentrading_mcp import obs
from opentrading_mcp.middleware import McpObservabilityMiddleware, RateLimiter, tool_name_of


def _app(limit_per_minute: int = 3) -> TestClient:
    async def ok(request):
        return JSONResponse({"ok": True})

    app = Starlette()
    app.add_middleware(RateLimiter, limit_per_minute=limit_per_minute)
    app.add_route("/mcp", ok, methods=["POST"])
    app.add_route("/healthz", ok, methods=["GET"])
    return TestClient(app, raise_server_exceptions=False)


def test_under_limit_passes():
    client = _app(limit_per_minute=3)
    for _ in range(3):
        assert client.post("/mcp", json={}).status_code == 200


def test_over_limit_returns_429_with_retry_after():
    client = _app(limit_per_minute=2)
    assert client.post("/mcp", json={}).status_code == 200
    assert client.post("/mcp", json={}).status_code == 200
    response = client.post("/mcp", json={})
    assert response.status_code == 429
    assert "retry-after" in response.headers
    assert response.json()["error"] == "rate_limited"


def test_healthz_never_limited():
    client = _app(limit_per_minute=1)
    for _ in range(5):
        assert client.get("/healthz").status_code == 200


def test_buckets_are_per_client_ip():
    client = _app(limit_per_minute=1)
    assert client.post("/mcp", json={}).status_code == 200
    assert client.post("/mcp", json={}).status_code == 429
    other = {"X-Forwarded-For": "9.9.9.9"}
    assert client.post("/mcp", json={}, headers=other).status_code == 200


def test_tool_name_extracted_from_jsonrpc_body():
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "market_snapshot", "arguments": {}},
    }
    assert tool_name_of(json.dumps(body).encode()) == "market_snapshot"
    assert tool_name_of(b"not json") == "unknown"
    assert tool_name_of(b'{"method": "initialize"}') == "initialize"


def test_observability_logs_tool_call_without_body(capsys):
    obs.reset()

    async def ok(request):
        return JSONResponse({"ok": True})

    app = Starlette()
    app.add_middleware(McpObservabilityMiddleware)
    app.add_route("/mcp", ok, methods=["POST"])
    app.add_route("/healthz", ok, methods=["GET"])
    client = TestClient(app, raise_server_exceptions=False)

    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "market_snapshot", "arguments": {"symbols": ["VCB"]}},
    }
    assert client.post("/mcp", json=body).status_code == 200
    assert client.get("/healthz").status_code == 200

    lines = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]
    assert len(lines) == 1
    assert lines[0]["tool"] == "market_snapshot"
    assert lines[0]["ok"] is True
    assert lines[0]["duration_ms"] >= 0
    assert "VCB" not in json.dumps(lines)
    assert 'tool_calls_total{tool="market_snapshot"} 1' in obs.render_metrics()
