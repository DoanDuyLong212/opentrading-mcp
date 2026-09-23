"""CLI: stdio default (all clients), --http for Streamable HTTP share."""

from __future__ import annotations

import argparse
import os

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
    return parser


def add_health_routes(server: FastMCP) -> None:
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    async def healthz(_request: Request) -> JSONResponse:
        return JSONResponse({"ok": True, "server": "opentrading"})

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
    server.custom_route("/.well-known/mcp.json", methods=["GET"])(server_card)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    server = create_server(args.preset)
    register_preset(server, args.preset)
    add_health_routes(server)
    if args.http:
        import uvicorn

        app = server.streamable_http_app()
        uvicorn.run(app, host="0.0.0.0", port=args.port)
    else:
        server.run(transport="stdio")
    return 0
