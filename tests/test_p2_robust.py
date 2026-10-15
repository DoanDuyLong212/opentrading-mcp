"""Unit tests for P2 hardening: limiter IP trust, obs cardinality (offline)."""

from __future__ import annotations

import asyncio

from starlette.requests import Request

from opentrading_mcp import obs
from opentrading_mcp.middleware import MAX_TRACKED_IPS, RateLimiter


def _req(peer: str, xff: str = "") -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "headers": [(b"x-forwarded-for", xff.encode())] if xff else [],
        "client": (peer, 1234),
    }
    return Request(scope)


def test_limiter_ignores_xff_from_public_peer():
    lim = RateLimiter(app=None)
    # Attacker-controlled header, direct (public) peer: must use the peer.
    assert lim._client_ip(_req("8.8.8.8", "1.1.1.1")) == "8.8.8.8"


def test_limiter_trusts_xff_behind_private_proxy():
    lim = RateLimiter(app=None)
    assert lim._client_ip(_req("10.0.0.5", "8.8.8.8")) == "8.8.8.8"
    # Garbage XFF falls back to the peer.
    assert lim._client_ip(_req("10.0.0.5", "not-an-ip")) == "10.0.0.5"


def test_limiter_bounds_ip_table():
    from collections import deque

    lim = RateLimiter(app=None)
    for i in range(MAX_TRACKED_IPS - 1):
        lim._hits[f"10.9.{i // 256}.{i % 256}"] = deque([0.0])

    async def hit(peer: str) -> None:
        scope = {
            "type": "http", "method": "POST", "path": "/mcp",
            "headers": [], "client": (peer, 1),
        }

        async def call_next(_request: Request) -> str:
            return "ok"

        await lim.dispatch(Request(scope), call_next)

    asyncio.run(hit("8.8.8.8"))
    asyncio.run(hit("8.8.4.4"))
    assert len(lim._hits) <= MAX_TRACKED_IPS


def test_obs_folds_overflow_into_other():
    obs.reset()
    for i in range(obs.MAX_SERIES + 50):
        obs.record_tool_call(f"evil-{i}", 1.0, ok=True)
    assert len(obs._calls) <= obs.MAX_SERIES + 1
    assert obs._calls.get("other", 0) == 50
    obs.reset()
