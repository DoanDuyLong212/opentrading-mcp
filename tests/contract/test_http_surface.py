"""The real HTTP app answers nothing without a token, except the listed public routes.

Builds the same app as ``opentrading-mcp --http`` (``cli.build_http_app``) and walks
every route it serves, so a route mounted later cannot slip past auth unnoticed: until
28/10/2026 a ``/sse`` mount served every tool with no token, no quota and no rate limit,
because each check gated only ``POST /mcp``.
"""

import pytest
from starlette.routing import Mount
from starlette.testclient import TestClient

from opentrading_mcp.cli import add_health_routes, build_http_app
from opentrading_mcp.middleware import PUBLIC_PATHS
from opentrading_mcp.server import create_server, register_all

TOKEN = "team-secret"
METHODS = ("GET", "POST", "PUT", "DELETE")


@pytest.fixture(scope="module")
def app():
    server = create_server()
    register_all(server)
    add_health_routes(server)
    return build_http_app(server)


@pytest.fixture
def client(app, monkeypatch):
    monkeypatch.setenv("MCP_BEARER_TEAM", TOKEN)
    monkeypatch.delenv("MCP_TOKEN", raising=False)
    monkeypatch.delenv("MCP_JWT_ISSUER", raising=False)
    monkeypatch.setenv("MCP_RATE_LIMIT_PER_MIN", "100000")
    return TestClient(app, raise_server_exceptions=False)


def _private_paths(app) -> list[str]:
    paths = []
    for route in app.routes:
        path = getattr(route, "path", None)
        if path is None or path in PUBLIC_PATHS:
            continue
        paths.append(f"{path}/anything" if isinstance(route, Mount) else path)
    return paths


def test_legacy_sse_transport_is_not_served(app):
    assert not [r for r in app.routes if getattr(r, "path", "").startswith("/sse")]


def test_every_private_route_needs_a_token(app, client):
    paths = _private_paths(app)
    assert "/mcp" in paths and "/metrics" in paths
    for path in paths:
        for method in METHODS:
            response = client.request(
                method, path, json={"jsonrpc": "2.0", "id": 1, "method": "ping"}
            )
            assert response.status_code == 401, f"{method} {path} -> {response.status_code}"


@pytest.mark.parametrize(
    "path", ["/sse", "/sse/sse", "/sse/messages/?session_id=x", "/messages/", "/not-a-route"]
)
def test_unknown_and_removed_routes_need_a_token_too(client, path):
    for method in METHODS:
        assert client.request(method, path).status_code == 401, f"{method} {path}"


def test_removed_sse_routes_are_gone_even_with_a_token(client):
    auth = {"Authorization": f"Bearer {TOKEN}"}
    assert client.get("/sse/sse", headers=auth).status_code == 404
    assert client.post("/sse/messages/?session_id=x", json={}, headers=auth).status_code == 404


def test_public_routes_answer_without_a_token(client):
    assert client.get("/healthz").status_code == 200
    assert client.get("/.well-known/mcp.json").status_code == 200
