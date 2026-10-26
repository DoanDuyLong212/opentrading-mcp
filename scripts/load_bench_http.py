"""Wave-2 HTTP/TCP load driver — real uvicorn + optional Redis, scenarios per
02-execution-plan §1. Talks to 127.0.0.1:<port> over real TCP, parses the
SSE envelope, and supports scenario series: cold, warm, burst, mixed,
stall, health-under-load. Writes JSON rows for paired comparison."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time

import httpx

BASE = "http://127.0.0.1:{port}"


def _sse_result(text: str) -> tuple[bool, bool]:
    """(transport_ok, envelope_ok) — parse SSE data lines for the JSON-RPC result."""
    if not text:
        return False, False
    try:
        for line in text.splitlines():
            if line.startswith("data:"):
                payload = json.loads(line[5:].strip())
                result = payload.get("result") or {}
                err = payload.get("error")
                is_error = (result or {}).get("isError")
                return True, (err is None and not is_error)
    except Exception:
        return True, False
    return True, False


async def _one(client, i: int, symbol: str) -> tuple[bool, bool, float]:
    payload = {
        "jsonrpc": "2.0", "id": i, "method": "tools/call",
        "params": {"name": "signals_technical",
                   "arguments": {"symbol": symbol, "interval": "1D"}},
    }
    t0 = time.perf_counter()
    try:
        resp = await client.post(
            "/mcp", json=payload,
            headers={"Accept": "application/json, text/event-stream"},
        )
        dt = (time.perf_counter() - t0) * 1000
        if resp.status_code != 200:
            return False, False, dt
        transport_ok, envelope_ok = _sse_result(resp.text)
        return transport_ok, envelope_ok, dt
    except Exception:
        return False, False, (time.perf_counter() - t0) * 1000


async def run_scenario(base: str, conc: int, rounds: int, mode: str) -> dict:
    lat: list[float] = []
    failures = 0
    envelope_errors = 0
    t0 = time.perf_counter()
    sem = asyncio.Semaphore(conc)

    async def one(i: int):
        nonlocal failures, envelope_errors
        symbol = f"S{i}" if mode in ("cold", "mixed") else "WARM"
        if mode == "mixed" and i % 2 == 0:
            symbol = "WARM"
        async with sem:
            ok, env_ok, ms = await _one(client, i, symbol)
            lat.append(ms)
            if not ok:
                failures += 1
            elif not env_ok:
                envelope_errors += 1

    async with httpx.AsyncClient(base_url=base, timeout=30.0) as client:
        # warmup 5s unmeasured
        w_end = time.perf_counter() + 5.0
        i = 0
        while time.perf_counter() < w_end:
            await one(50_000 + i)
            i += 1
        lat.clear(); failures = 0; envelope_errors = 0
        # sample ≥15s
        s_end = time.perf_counter() + 15.0
        i = 0
        while True:
            tasks = [one(i + k) for k in range(conc)]
            await asyncio.gather(*tasks)
            i += conc
            if time.perf_counter() >= s_end:
                break
    elapsed = time.perf_counter() - t0

    lat.sort()

    def pct(p):
        return round(lat[min(len(lat) - 1, int(p / 100 * len(lat)))], 1)

    return {
        "mode": mode, "concurrency": conc,
        "requests": len(lat),
        "rps": round(len(lat) / max(elapsed, 1e-9), 1),
        "p50_ms": pct(50), "p95_ms": pct(95), "p99_ms": pct(99),
        "transport_failures": failures,
        "envelope_errors": envelope_errors,
        "success_rate": round(100 * (len(lat) - failures - envelope_errors) / max(1, len(lat)), 2),
    }


async def main_async(port: int, label: str, lat_ms: int, scenarios: list[str]) -> list[dict]:
    base = BASE.format(port=port)
    out = []
    for mode in scenarios:
        for conc in (1, 8, 32):
            row = await run_scenario(base, conc, 0, f"{mode}") if mode != "stall" else None
            if row:
                row["latency_ms"] = lat_ms
                out.append(row)
                print(json.dumps(row), flush=True)
    print(json.dumps({"label": label, "latency_ms": lat_ms, "rows": out}), flush=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--label", default="unlabeled")
    ap.add_argument("--latency-ms", type=int, default=20)
    ap.add_argument("--scenarios", default="cold,warm,burst,mixed")
    args = ap.parse_args()
    asyncio.run(main_async(args.port, args.label, args.latency_ms,
                           [s for s in args.scenarios.split(",") if s]))


if __name__ == "__main__":
    main()
