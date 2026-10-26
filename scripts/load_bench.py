"""Paired HTTP load benchmark for the MCP server (full-review Wave-B).

Drives the real ASGI app (FastMCP streamable HTTP, stateless mode) with
concurrent tools/call requests for a compute-heavy offline tool, with the
upstream provider patched to a deterministic synthetic fixture — no live
network. Measures p50/p95/p99 latency, RPS and success rate per concurrency
level (1/8/32).

Usage:
  uv run python scripts/load_bench.py --rounds 40 --levels 1,8,32

Paired run: run it once on the fix branch, once in a baseline worktree
(git worktree add /tmp/mcp-baseline 3932cba && uv sync there), same flags.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time

sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__file__), "..", "src"))

import httpx
import numpy as np

CANDLE_BARS = 300  # ~1.2 years of daily bars per symbol


def _synthetic_candles(symbol: str, n: int = CANDLE_BARS) -> list[dict]:
    seed = int.from_bytes(hashlib.sha256(symbol.encode()).digest()[:4], "big")
    closes = list(50 + np.cumsum(np.random.default_rng(seed).normal(0, 0.5, n)))
    import datetime as dt

    rows, day = [], dt.date(2025, 1, 1)
    for c in closes:
        while day.weekday() >= 5:
            day += dt.timedelta(days=1)
        rows.append(
            {"t": day.isoformat(), "o": round(c * 0.99, 2), "h": round(c * 1.01, 2),
             "l": round(c * 0.98, 2), "c": round(c, 2), "v": 1000.0}
        )
        day += dt.timedelta(days=1)
    return rows


def _patch_offline() -> None:
    """Deterministic fake upstream — no live provider calls during the bench."""
    from opentrading_mcp.providers import vnstock as vn_p

    vn_p.quote_history = lambda symbol, days, iv=None: _synthetic_candles(symbol)[: max(days, 30)]
    vn_p.equity_quote_batch = lambda symbols: [
        {"symbol": s, "close": 50.0, "change": 0.0} for s in symbols
    ]
    try:
        from opentrading_mcp.providers import dnse as dnse_p

        dnse_p.ws_snapshot = lambda symbols=None: {"mock": True}
    except Exception:
        pass


def _build_app():
    from opentrading_mcp.server import create_server, register_all

    server = create_server("all")
    register_all(server)
    return server.streamable_http_app()


async def _call_tool(client: httpx.AsyncClient, i: int) -> tuple[bool, float]:
    payload = {
        "jsonrpc": "2.0", "id": i, "method": "tools/call",
        "params": {"name": "signals_technical",
                   "arguments": {"symbol": f"S{i % 7}", "interval": "1D"}},
    }
    t0 = time.perf_counter()
    try:
        resp = await client.post(
            "/mcp", json=payload,
            headers={"Accept": "application/json, text/event-stream"},
        )
        elapsed = (time.perf_counter() - t0) * 1000
        if resp.status_code != 200:
            return False, elapsed
        from load_bench_http import _decode

        transport, ok, env = _decode(resp.text)
        return bool(transport and ok and env["data"].get("rsi14") is not None), elapsed
    except Exception:
        return False, (time.perf_counter() - t0) * 1000


async def run_level(app, concurrency: int, rounds: int) -> dict:
    transport = httpx.ASGITransport(app=app)
    latencies: list[float] = []
    failures = 0
    sem = asyncio.Semaphore(concurrency)

    async def one(i: int):
        nonlocal failures
        async with sem:
            ok, ms = await _call_tool(client, i)
            latencies.append(ms)
            if not ok:
                failures += 1

    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        # warmup: 5 requests unmeasured (also resets the failure counter)
        warmup_failures = 0
        for i in range(5):
            ok, _ = await _call_tool(client, 10_000 + i)
            warmup_failures += 0 if ok else 1
        latencies.clear()
        failures = 0
        t0 = time.perf_counter()
        await asyncio.gather(*(one(i) for i in range(rounds)))
    elapsed = time.perf_counter() - t0

    lat_sorted = sorted(latencies)

    def pct(p: float) -> float:
        idx = min(len(lat_sorted) - 1, int(p / 100 * len(lat_sorted)))
        return lat_sorted[idx]

    return {
        "concurrency": concurrency,
        "rounds": rounds,
        "rps": round(len(latencies) / elapsed, 2),
        "p50_ms": round(pct(50), 1),
        "p95_ms": round(pct(95), 1),
        "p99_ms": round(pct(99), 1),
        "success_rate": round(100 * (len(latencies) - failures) / max(1, len(latencies)), 2),
    }


async def main_async(levels: list[int], rounds: int) -> list[dict]:
    import os

    # the ASGI bench presents Host: localhost — allow it explicitly (S05-era
    # transport_security() only enables settings when MCP_ALLOWED_HOSTS is set,
    # but the MCP SDK's default DNS-rebinding guard still validates Host)
    os.environ["MCP_ALLOWED_HOSTS"] = "localhost,127.0.0.1"
    _patch_offline()
    app = _build_app()
    out = []
    # the streamable-HTTP transport needs its lifespan (task group) running
    async with app.router.lifespan_context(app):
        for conc in levels:
            row = await run_level(app, conc, rounds)
            out.append(row)
            print(json.dumps(row))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", default="1,8,32")
    ap.add_argument("--rounds", type=int, default=40)
    args = ap.parse_args()
    levels = [int(x) for x in args.levels.split(",")]
    rounds = args.rounds
    rows = asyncio.run(main_async(levels, rounds))
    print(json.dumps({"label": __import__("os").environ.get("BENCH_LABEL", "unlabeled"),
                      "rows": rows}))


if __name__ == "__main__":
    main()
