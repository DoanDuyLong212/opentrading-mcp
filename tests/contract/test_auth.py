"""Phase 2 auth contract tests: bearer, JWT resource-server, quota, host enforce."""

import time

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from opentrading_mcp import auth_oauth
from opentrading_mcp.middleware import AuthMiddleware


def _app(**kwargs) -> TestClient:
    async def ok(request):
        user = getattr(request.state, "user_id", None)
        return JSONResponse({"ok": True, "user": user})

    app = Starlette()
    app.add_middleware(AuthMiddleware, **kwargs)
    app.add_route("/mcp", ok, methods=["POST"])
    app.add_route("/healthz", ok, methods=["GET"])
    return TestClient(app, raise_server_exceptions=False)


def test_open_when_nothing_configured(monkeypatch):
    monkeypatch.delenv("MCP_BEARER_TEAM", raising=False)
    monkeypatch.delenv("MCP_TOKEN", raising=False)
    monkeypatch.delenv("MCP_JWT_ISSUER", raising=False)
    client = _app()
    assert client.post("/mcp", json={}).status_code == 200


def test_team_bearer_accepted(monkeypatch):
    monkeypatch.setenv("MCP_BEARER_TEAM", "s3cret")
    client = _app()
    response = client.post("/mcp", json={}, headers={"Authorization": "Bearer s3cret"})
    assert response.status_code == 200
    assert response.json()["user"] == "team"


def test_wrong_bearer_rejected_with_www_authenticate(monkeypatch):
    monkeypatch.setenv("MCP_BEARER_TEAM", "s3cret")
    client = _app()
    response = client.post("/mcp", json={}, headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers
    assert response.json()["error"] == "authentication_failed"


def test_missing_bearer_rejected(monkeypatch):
    monkeypatch.setenv("MCP_BEARER_TEAM", "s3cret")
    client = _app()
    assert client.post("/mcp", json={}).status_code == 401


def test_healthz_bypasses_auth(monkeypatch):
    monkeypatch.setenv("MCP_BEARER_TEAM", "s3cret")
    client = _app()
    assert client.get("/healthz").status_code == 200


def test_metrics_requires_auth(monkeypatch):
    async def ok(request):
        from starlette.responses import JSONResponse

        return JSONResponse({"ok": True})

    from starlette.applications import Starlette
    from starlette.testclient import TestClient

    from opentrading_mcp.middleware import AuthMiddleware

    monkeypatch.setenv("MCP_BEARER_TEAM", "s3cret")
    app = Starlette()
    app.add_middleware(AuthMiddleware)
    app.add_route("/metrics", ok, methods=["GET"])
    app.add_route("/healthz", ok, methods=["GET"])
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert client.get("/healthz").status_code == 200


def _rsa_keypair():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return private, public


def _mint(private_pem: str, **claims) -> str:
    import jwt

    now = int(time.time())
    payload = {"iss": "https://auth.example.test", "sub": "u1", "exp": now + 600, **claims}
    return jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": "k1"})


def _jwks_dict(public_pem: str) -> dict:
    import base64

    from cryptography.hazmat.primitives import serialization

    key = serialization.load_pem_public_key(public_pem.encode())
    numbers = key.public_numbers()
    n = base64.urlsafe_b64encode(numbers.n.to_bytes(256, "big")).rstrip(b"=").decode()
    e = base64.urlsafe_b64encode(numbers.e.to_bytes(3, "big")).rstrip(b"=").decode()
    return {"keys": [{"kty": "RSA", "kid": "k1", "use": "sig", "n": n, "e": e}]}


def _jwt_env(monkeypatch, public_pem: str):
    jwks = _jwks_dict(public_pem)
    monkeypatch.setenv("MCP_JWT_ISSUER", "https://auth.example.test")
    monkeypatch.setenv("MCP_JWT_AUDIENCE", "opentrading-mcp")
    monkeypatch.delenv("MCP_BEARER_TEAM", raising=False)
    monkeypatch.delenv("MCP_TOKEN", raising=False)
    monkeypatch.setattr(auth_oauth, "_fetch_jwks", lambda url: jwks)


def test_valid_jwt_accepted_with_sub(monkeypatch):
    private, public = _rsa_keypair()
    _jwt_env(monkeypatch, public)
    client = _app()
    token = _mint(private, aud="opentrading-mcp")
    response = client.post("/mcp", json={}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["user"] == "u1"


def test_expired_jwt_rejected(monkeypatch):
    import jwt as pyjwt

    private, public = _rsa_keypair()
    _jwt_env(monkeypatch, public)
    token = pyjwt.encode(
        {"iss": "https://auth.example.test", "sub": "u1", "aud": "opentrading-mcp", "exp": 1},
        private,
        algorithm="RS256",
        headers={"kid": "k1"},
    )
    client = _app()
    assert (
        client.post("/mcp", json={}, headers={"Authorization": f"Bearer {token}"}).status_code
        == 401
    )


def test_wrong_audience_rejected(monkeypatch):
    private, public = _rsa_keypair()
    _jwt_env(monkeypatch, public)
    token = _mint(private, aud="someone-else")
    client = _app()
    assert (
        client.post("/mcp", json={}, headers={"Authorization": f"Bearer {token}"}).status_code
        == 401
    )


def test_quota_exceeded_returns_429(monkeypatch):
    from opentrading_mcp import quota as quota_mod

    monkeypatch.setenv("DATABASE_URL", "postgresql://test/test")

    async def fake_factory():
        class FakeConn:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def execute(self, query, params=None):
                # S04: BEGIN / advisory lock / COMMIT all land here
                return None

            async def fetchone(self, query, params):
                return (1000, 1000)  # quota_day, used

        return FakeConn()

    monkeypatch.setattr(quota_mod, "_connect", fake_factory)
    import asyncio

    allowed, retry_after = asyncio.run(quota_mod.check_and_record("u1", "market_snapshot", 15))
    assert allowed is False
    assert retry_after > 0


def test_quota_allows_under_limit(monkeypatch):
    from opentrading_mcp import quota as quota_mod

    monkeypatch.setenv("DATABASE_URL", "postgresql://test/test")
    seen = {}

    async def fake_factory():
        class FakeConn:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def fetchone(self, query, params):
                if query.strip().upper().startswith("SELECT"):
                    return (1000, 10)
                seen["upsert"] = True
                return None

            async def execute(self, query, params=None):
                seen["upsert"] = True

        return FakeConn()

    monkeypatch.setattr(quota_mod, "_connect", fake_factory)
    import asyncio

    allowed, _ = asyncio.run(quota_mod.check_and_record("u1", "market_snapshot", 15))
    assert allowed is True
    assert seen.get("upsert") is True


def test_public_http_requires_allowed_hosts_or_flag():
    import argparse

    from opentrading_mcp.cli import require_public_host_args

    args = argparse.Namespace(allow_all_hosts=False)
    assert "MCP_ALLOWED_HOSTS" in (require_public_host_args(args, {}) or "")
    args = argparse.Namespace(allow_all_hosts=True)
    assert require_public_host_args(args, {"MCP_ALLOWED_HOSTS": ""}) is None


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
