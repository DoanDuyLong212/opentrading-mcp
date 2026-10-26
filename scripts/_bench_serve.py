"""Loopback-only, offline TCP benchmark server; never use this wrapper in production.

BENCH_SOURCE_ROOT optionally points to a baseline checkout's src directory.
/__bench/state and /__bench/config expose fixture metrics and injected latency.
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import os
import sys
import threading
import time

sys.path.insert(0, os.environ.get("BENCH_SOURCE_ROOT", os.path.join(
    os.path.dirname(__file__), "..", "src")))


def _synthetic_candles(symbol: str, n: int = 300) -> list[dict]:
    import datetime as dt

    import numpy as np

    seed = int.from_bytes(hashlib.sha256(symbol.encode()).digest()[:4], "big")
    closes = 50 + np.cumsum(np.random.default_rng(seed).normal(0, 0.5, n))
    rows, day = [], dt.date(2025, 1, 1)
    for c in closes:
        while day.weekday() >= 5:
            day += dt.timedelta(days=1)
        rows.append({"t": day.isoformat(), "o": round(c * 0.99, 2),
                     "h": round(c * 1.01, 2), "l": round(c * 0.98, 2),
                     "c": round(c, 2), "v": 1000.0})
        day += dt.timedelta(days=1)
    return rows


def build_app(port: int):
    os.environ["DATABASE_URL"] = ""
    os.environ["MCP_ALLOWED_HOSTS"] = f"localhost:{port},127.0.0.1:{port}"
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    from opentrading_mcp.providers import dnse as dnse_p
    from opentrading_mcp.providers import store
    from opentrading_mcp.providers import vnstock as vn_p
    from opentrading_mcp.server import create_server, register_all
    from opentrading_mcp.tools import shared

    lock = threading.Lock()
    metrics = {"latency_ms": float(os.environ.get("BENCH_LATENCY_MS", "20")),
               "active": 0, "max_active": 0, "provider_calls": 0}

    def instrument(fn):
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            with lock:
                metrics["active"] += 1
                metrics["provider_calls"] += 1
                metrics["max_active"] = max(metrics["max_active"], metrics["active"])
                latency = metrics["latency_ms"]
            try:
                time.sleep(latency / 1000)
                return fn(*args, **kwargs)
            finally:
                with lock:
                    metrics["active"] -= 1
        return wrapped

    vn_p.quote_history = instrument(
        lambda symbol, days, iv=None: _synthetic_candles(symbol)[:max(int(days), 30)])
    vn_p.equity_quote_batch = instrument(
        lambda symbols: [{"symbol": s, "close": 50., "change": 0.} for s in symbols])
    vn_p.equity_ratios = instrument(lambda symbol, kind, limit=5: {
        "periods": ["2025"], "frequency": "annual",
        "ratios": [{"item_id": "roe", "values": {"2025": 0.15}, "basis": "annual"}]})
    dnse_p.ws_snapshot = instrument(lambda symbols=None: {"mock": True, "symbols": symbols})
    server = create_server("all")
    register_all(server)
    app = server.streamable_http_app()

    async def state(request):
        with lock:
            body = dict(metrics)
        body.update(pending=shared._pending, redis_configured=bool(os.environ.get("REDIS_URL")),
                    redis_client_active=store._client is not None,
                    redis_backoff=store._down_until > time.monotonic())
        return JSONResponse(body)

    async def configure(request):
        body = await request.json()
        with lock:
            metrics["latency_ms"] = max(0., min(5000., float(body["latency_ms"])))
            metrics["max_active"] = metrics["active"]
            metrics["provider_calls"] = 0
        return await state(request)

    app.routes.extend([Route("/__bench/state", state),
                       Route("/__bench/config", configure, methods=["POST"])])
    return app


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    import uvicorn

    uvicorn.run(build_app(args.port), host="127.0.0.1", port=args.port,
                log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
