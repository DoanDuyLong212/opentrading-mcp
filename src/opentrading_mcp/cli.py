"""CLI: stdio default (all clients), --http for Streamable HTTP share."""

from __future__ import annotations

import argparse
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.server import PRESETS, create_server, register_preset


def default_port() -> int:
    try:
        return int(os.environ.get("PORT", "8102"))
    except ValueError:
        return 8102


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="opentrading-mcp")
    parser.add_argument("serve", nargs="?", default="serve")
    parser.add_argument("--preset", default="market", choices=list(PRESETS))
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
        deep = request.query_params.get("deep") == "1"
        code, body = await health_report(deep=deep)
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
    server.custom_route("/metrics", methods=["GET"])(metrics)
    server.custom_route("/.well-known/mcp.json", methods=["GET"])(server_card)


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
        return run_verify(args.target, args.preset, args.url)
    server = create_server(args.preset)
    register_preset(server, args.preset)
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
        app.add_middleware(RateLimiter, limit_per_minute=rate_limit_per_minute())
        app.add_middleware(AuthMiddleware)
        app.add_middleware(McpObservabilityMiddleware)
        uvicorn.run(app, host="0.0.0.0", port=args.port)
    else:
        server.run(transport="stdio")
    return 0


def run_verify(target: str, preset: str, url: str) -> int:
    import asyncio

    from opentrading_mcp.server import PRESETS
    from opentrading_mcp.verify_matrix import run_preset_remote, run_preset_stdio

    async def collect() -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        presets = list(PRESETS) if preset == "all" else [preset]
        if target in ("local", "both"):
            for item in presets:
                rows.extend(await run_preset_stdio(item))
        if target in ("remote", "both"):
            rows.extend(await run_preset_remote(url, "market"))
        return rows

    rows = asyncio.run(collect())
    failures = 0
    print(
        f"{'preset':<7} {'tool':<24} {'transport':<9} {'ok':<4} {'secs':>6}  {'avail':<11}  detail"
    )
    for row in rows:
        mark = "PASS" if row["ok"] else "FAIL"
        if not row["ok"]:
            failures += 1
        print(
            f"{row['preset']:<7} {row['tool']:<24} {row['transport']:<9} "
            f"{mark:<4} {row['seconds']:>6}  {row['availability']:<11}  {row['detail'][:90]}"
        )
    print(f"\n{len(rows) - failures}/{len(rows)} passed")
    return 1 if failures else 0
