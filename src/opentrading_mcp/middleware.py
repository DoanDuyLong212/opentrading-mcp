"""Starlette middleware: rate limiting (Phase 0), auth (Phase 2), observability (Phase 1)."""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# The only routes served without a token, rate limit or quota. Everything else, including
# any route mounted later, is gated: allowlist what is public, never list what is private.
PUBLIC_PATHS = ("/healthz", "/readyz", "/.well-known/mcp.json")

WINDOW_SECONDS = 60.0


class RateLimiter(BaseHTTPMiddleware):
    """Per-IP sliding-window limiter for every route except ``PUBLIC_PATHS``.

    Health/discovery routes are never limited. Client IP prefers
    X-Forwarded-For (Render proxy) then the direct peer address.
    """

    MAX_TRACKED_CLIENTS = 10_000  # P04: bound memory against spoofed XFF floods

    def __init__(self, app: Any, limit_per_minute: int = 120) -> None:
        super().__init__(app)
        self.limit_per_minute = max(1, int(limit_per_minute))
        self._hits: dict[str, deque[float]] = {}

    def _client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if forwarded:
            return forwarded
        client = request.client
        return client.host if client else "unknown"

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)
        now = time.monotonic()
        ip = self._client_ip(request)
        if ip not in self._hits and len(self._hits) >= self.MAX_TRACKED_CLIENTS:
            # P04: evict expired/oldest buckets before admitting a new key so a
            # spoofed-XFF flood cannot grow the map without bound.
            cutoff_now = now - WINDOW_SECONDS
            expired = [k for k, dq in self._hits.items() if not dq or dq[-1] <= cutoff_now]
            for k in expired:
                self._hits.pop(k, None)
            while len(self._hits) >= self.MAX_TRACKED_CLIENTS:
                self._hits.pop(next(iter(self._hits)))
        bucket = self._hits.setdefault(ip, deque())
        cutoff = now - WINDOW_SECONDS
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= self.limit_per_minute:
            retry_after = max(1, int(bucket[0] + WINDOW_SECONDS - now))
            return JSONResponse(
                {"error": "rate_limited", "retry_after": retry_after},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)
        return await call_next(request)


def rate_limit_per_minute() -> int:
    try:
        return max(1, int(os.environ.get("MCP_RATE_LIMIT_PER_MIN", "120")))
    except ValueError:
        return 120


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _unauthorized(message: str) -> JSONResponse:
    return JSONResponse(
        {"error": "authentication_failed", "message": message},
        status_code=401,
        headers={
            "WWW-Authenticate": (
                'Bearer realm="opentrading-mcp", error="invalid_token", '
                'error_description="Provide the team bearer token or a JWT '
                'from the configured issuer; see server docs"'
            )
        },
    )


class AuthMiddleware(BaseHTTPMiddleware):
    """Gate every route except ``PUBLIC_PATHS`` behind team bearer or validated JWT.

    Open when neither is configured (local stdio-style dev). Team bearer
    callers bypass quota; JWT subjects are quota-checked per user/day.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Default deny: every method on every route needs a token unless it is listed as
        # public. Gating only POST /mcp once left a later /sse mount fully open (28/10/2026).
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)
        from opentrading_mcp import auth, auth_oauth, quota

        presented = _bearer_token(request)
        team = auth.get_bearer()
        user_id: str | None = None
        if team and presented and hmac.compare_digest(presented, team):
            user_id = "team"
        elif auth_oauth.is_configured():
            if presented is None:
                return _unauthorized("missing bearer token")
            try:
                claims = await asyncio.to_thread(auth_oauth.validate_jwt, presented)
            except auth_oauth.JwtError as exc:
                return _unauthorized(str(exc))
            subject = claims.get("sub")
            if not isinstance(subject, str) or not subject:
                return _unauthorized("token has no subject")
            user_id = subject
        elif team:
            return _unauthorized("invalid or missing bearer token")
        else:
            return await call_next(request)
        request.state.user_id = user_id
        if user_id != "team" and request.method == "POST":
            try:
                raw = await request.body()
            except Exception:
                raw = b""
            allowed, retry_after = await quota.check_and_record(user_id, tool_name_of(raw), 0.0)
            if not allowed:
                return JSONResponse(
                    {"error": "quota_exceeded", "retry_after": retry_after},
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                )

        async def receive() -> dict[str, Any]:
            try:
                raw_body = await request.body()
            except Exception:
                raw_body = b""
            return {"type": "http.request", "body": raw_body, "more_body": False}

        return await call_next(Request(request.scope, receive))


def tool_name_of(body: bytes) -> str:
    """Best-effort tool name from a JSON-RPC body; never raises."""
    try:
        payload = json.loads(body)
    except (ValueError, TypeError):
        return "unknown"
    if not isinstance(payload, dict):
        return "unknown"
    if payload.get("method") == "tools/call":
        params = payload.get("params")
        if isinstance(params, dict):
            name = params.get("name")
            if isinstance(name, str):
                return name
    method = payload.get("method")
    if isinstance(method, str):
        return method
    return "unknown"


class McpObservabilityMiddleware(BaseHTTPMiddleware):
    """One JSON log line + metrics per POST /mcp call.

    Only the tool name, duration and HTTP outcome are recorded — never
    arguments, results or headers (upstream data may contain PII).
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method != "POST" or request.url.path != "/mcp":
            return await call_next(request)
        from opentrading_mcp import obs

        try:
            raw = await request.body()
        except Exception:
            raw = b""
        tool = tool_name_of(raw)

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": raw, "more_body": False}

        replayed = Request(request.scope, receive)
        started = time.monotonic()
        try:
            response = await call_next(replayed)
        except Exception:
            elapsed_ms = (time.monotonic() - started) * 1000
            obs.record_tool_call(tool, elapsed_ms, ok=False, error_code="exception")
            obs.log_tool_call(tool, elapsed_ms, ok=False, error_code="exception")
            raise
        elapsed_ms = (time.monotonic() - started) * 1000
        ok = response.status_code < 500
        error_code = "" if ok else f"http_{response.status_code}"
        obs.record_tool_call(tool, elapsed_ms, ok=ok, error_code=error_code)
        obs.log_tool_call(tool, elapsed_ms, ok=ok, error_code=error_code)
        return response
