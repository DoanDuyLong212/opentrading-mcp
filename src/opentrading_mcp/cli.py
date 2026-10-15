"""CLI: stdio default (all clients), --http for Streamable HTTP share."""

from __future__ import annotations

import argparse
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.server import create_server, register_all


def default_port() -> int:
    try:
        return int(os.environ.get("PORT", "8102"))
    except ValueError:
        return 8102


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="opentrading-mcp")
    parser.add_argument("serve", nargs="?", default="serve")
    parser.add_argument(
        "--preset",
        default="all",
        help="deprecated alias (giữ tương thích): server luôn expose full tools",
    )
    parser.add_argument(
        "--http", action="store_true", help="serve Streamable HTTP instead of stdio"
    )
    parser.add_argument("--port", type=int, default=default_port())
    parser.add_argument("--path", default="/mcp")
    parser.add_argument(
        "--allow-all-hosts",
        action="store_true",
        help="serve HTTP without MCP_ALLOWED_HOSTS DNS-rebinding protection (local/LAN only)",
    )
    parser.add_argument(
        "--target",
        default="local",
        choices=["local", "remote", "both"],
        help="verify target (verify command only)",
    )
    parser.add_argument(
        "--url",
        default="https://opentrading-mcp-web.onrender.com/mcp",
        help="remote URL (verify --target remote|both)",
    )
    return parser


def add_health_routes(server: FastMCP) -> None:
    from starlette.requests import Request
    from starlette.responses import JSONResponse, PlainTextResponse

    from opentrading_mcp.health import health_report

    async def healthz(request: Request) -> JSONResponse:
        # Liveness only: the host (Render: 5s timeout) restarts us when this is slow, so it
        # must not wait on Redis/Postgres or the shared thread pool. Dependencies are
        # checked by /readyz, or /healthz?full=1 (and ?deep=1 adds upstream probes).
        deep = request.query_params.get("deep") == "1"
        if not deep and request.query_params.get("full") != "1":
            return JSONResponse({"ok": True, "server": "opentrading"})
        code, body = await health_report(deep=deep)
        return JSONResponse(body, status_code=code)

    async def readyz(request: Request) -> JSONResponse:
        code, body = await health_report(deep=request.query_params.get("deep") == "1")
        return JSONResponse(body, status_code=code)

    async def metrics(_request: Request) -> PlainTextResponse:
        # NOTE Phase 2: protect with the same auth as /mcp (counters leak tool names).
        from opentrading_mcp import obs

        return PlainTextResponse(obs.render_metrics(), media_type="text/plain")

    async def server_card(_request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "name": "opentrading",
                "description": "Vietnamese market research MCP (team -> public)",
                "endpoint": "/mcp",
                "transports": ["streamable-http", "stdio"],
            }
        )

    server.custom_route("/healthz", methods=["GET"])(healthz)
    server.custom_route("/readyz", methods=["GET"])(readyz)
    server.custom_route("/metrics", methods=["GET"])(metrics)
    server.custom_route("/.well-known/mcp.json", methods=["GET"])(server_card)


def warm_up() -> None:
    """Import vnstock (and the matplotlib it drags in) before the first tool needs it.

    The first import takes seconds of CPU on a small host; paid inside the first burst
    of tool calls, it stalled every request at once. Errors are ignored: tools report
    a missing or broken vnstock themselves.
    """
    import logging
    import time

    started = time.monotonic()
    try:
        import vnstock.common  # noqa: F401  (imports vnstock too)
    except Exception as exc:  # pragma: no cover - depends on the environment
        logging.getLogger(__name__).warning("warm-up import failed: %s", exc)
        return
    elapsed = time.monotonic() - started
    logging.getLogger(__name__).warning("warm-up: vnstock ready in %.1fs", elapsed)


def start_warm_up() -> None:
    """Warm up in the background (MCP_WARMUP=0 turns it off), so the port opens at once."""
    import os
    import threading

    if os.environ.get("MCP_WARMUP", "1") == "0":
        return
    threading.Thread(target=warm_up, name="warm-up", daemon=True).start()


def require_public_host_args(args: Any, env: dict[str, str]) -> str | None:
    """Refuse public HTTP serving without explicit host consent.

    Returns an error message, or None when serving may proceed.
    """
    if bool(getattr(args, "allow_all_hosts", False)):
        return None
    if (env.get("MCP_ALLOWED_HOSTS") or "").strip():
        return None
    return (
        "Refusing to serve HTTP without MCP_ALLOWED_HOSTS "
        "(DNS-rebinding protection). Set MCP_ALLOWED_HOSTS to your public "
        "hostname or pass --allow-all-hosts for local/LAN-only use."
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.serve == "verify":
        return run_verify(args.target, args.url)
    if args.serve == "cycle-refresh":
        # Seed/refresh the cycle tables against DATABASE_URL (never automatic).
        from os import environ

        from opentrading_mcp.cycle_refresh import main as cycle_refresh

        return cycle_refresh(only=environ.get("CYCLE_REFRESH_ONLY") or None)
    if getattr(args, "preset", "all") != "all":
        import warnings

        warnings.warn(
            "--preset deprecated: full tools only", DeprecationWarning, stacklevel=2
        )
    server = create_server()
    register_all(server)
    add_health_routes(server)
    if args.http:
        import os

        import uvicorn

        host_error = require_public_host_args(args, dict(os.environ))
        if host_error is not None:
            parser.error(host_error)
        from opentrading_mcp.middleware import (
            AuthMiddleware,
            McpObservabilityMiddleware,
            RateLimiter,
            rate_limit_per_minute,
        )

        app = server.streamable_http_app()
        app.mount("/sse", server.sse_app())
        app.add_middleware(RateLimiter, limit_per_minute=rate_limit_per_minute())
        app.add_middleware(AuthMiddleware)
        app.add_middleware(McpObservabilityMiddleware)
        start_warm_up()
        from opentrading_mcp.loops import start_in_web_loops

        start_in_web_loops()
        uvicorn.run(app, host="0.0.0.0", port=args.port)
    else:
        server.run(transport="stdio")
    return 0


def run_verify(target: str, url: str) -> int:
    import asyncio

    from opentrading_mcp.verify_matrix import run_remote_all, run_stdio_all

    async def collect() -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if target in ("local", "both"):
            rows.extend(await run_stdio_all())
        if target in ("remote", "both"):
            rows.extend(await run_remote_all(url))
        return rows

    rows = asyncio.run(collect())
    failures = 0
    print(f"{'tool':<24} {'transport':<9} {'ok':<4} {'secs':>6}  {'avail':<11}  detail")
    for row in rows:
        mark = "PASS" if row["ok"] else "FAIL"
        if not row["ok"]:
            failures += 1
        print(
            f"{row['tool']:<24} {row['transport']:<9} "
            f"{mark:<4} {row['seconds']:>6}  {row['availability']:<11}  {row['detail'][:90]}"
        )
    print(f"\n{len(rows) - failures}/{len(rows)} passed")
    return 1 if failures else 0
