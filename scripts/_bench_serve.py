"""Benchmark serve wrapper — Wave 2 (09-load-benchmark-http).

Offline deterministic providers + optional fixed latency per provider call,
real uvicorn/TCP on 127.0.0.1:<port>. Env:
  BENCH_LATENCY_MS  fixed sleep before each provider call (default 0)
  MCP_ALLOWED_HOSTS is set here so loopback TCP passes the SDK host guard.
"""

from __future__ import annotations

import argparse
import functools
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

os.environ.setdefault(
    "MCP_ALLOWED_HOSTS",
    "localhost,127.0.0.1,"
    + ",".join(f"localhost:{p},127.0.0.1:{p}" for p in (8765, 8766, 8767, 8768)),
)


def _synthetic_candles(symbol: str, n: int = 300) -> list[dict]:
    import datetime as dt

    import numpy as np

    seed = abs(hash(symbol)) % (2**32)
    closes = list(50 + np.cumsum(np.random.default_rng(seed).normal(0, 0.5, n)))
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()

    from opentrading_mcp.providers import dnse as dnse_p
    from opentrading_mcp.providers import vnstock as vn_p

    lat_ms = float(os.environ.get("BENCH_LATENCY_MS", "0"))

    def _with_latency(fn):
        if lat_ms <= 0:
            return fn
        @functools.wraps(fn)
        def wrapped(*a, **k):
            time.sleep(lat_ms / 1000.0)
            return fn(*a, **k)
        return wrapped

    vn_p.quote_history = _with_latency(
        lambda symbol, days, iv=None: _synthetic_candles(symbol)[: max(int(days), 30)]
    )
    vn_p.equity_quote_batch = _with_latency(
        lambda symbols: [{"symbol": s, "close": 50.0, "change": 0.0} for s in symbols]
    )
    vn_p.equity_ratios = _with_latency(
        lambda symbol, kind, limit=5: {
            "periods": ["2025"],
            "ratios": [{"item_id": "roe", "values": {"2025": 0.15}, "basis": "annual"}],
            "frequency": "annual",
        }
    )
    dnse_p.ws_snapshot = _with_latency(lambda symbols=None: {"mock": True, "symbols": symbols})

    from opentrading_mcp.server import create_server, register_all

    server = create_server("all")
    register_all(server)

    os.environ["DATABASE_URL"] = ""  # no DB in the bench (quota passthrough)
    import uvicorn

    uvicorn.run(
        server.streamable_http_app(), host="127.0.0.1", port=args.port,
        log_level="warning", access_log=False,
    )


if __name__ == "__main__":
    main()
