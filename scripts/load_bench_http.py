"""TCP/SSE benchmark with application-envelope validation and raw JSON evidence.

Default samples: warmup 5s + measured >=15s. Shorter runs are labelled smoke.
Redis outage is only allowed against a container labelled opentrading-bench=1.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from pathlib import Path

import httpx

MODES = {"cold", "warm", "burst", "mixed", "stall", "health-under-load",
         "redis-down", "peer"}


def _envelope(result: dict) -> dict | None:
    structured = result.get("structuredContent")
    if isinstance(structured, dict) and "availability" in structured:
        return structured
    for block in result.get("content") or []:
        if block.get("type") == "text":
            try:
                candidate = json.loads(block["text"])
            except (ValueError, KeyError, TypeError):
                continue
            if isinstance(candidate, dict) and "availability" in candidate:
                return candidate
    return None


def _decode(text: str) -> tuple[bool, bool, dict | None]:
    try:
        payloads = ([json.loads(text)] if text.lstrip().startswith("{") else
                    [json.loads(line[5:].strip()) for line in text.splitlines()
                     if line.startswith("data:")])
        for payload in payloads:
            if "result" not in payload and "error" not in payload:
                continue  # ignore notifications before the response
            result = payload.get("result") or {}
            env = _envelope(result)
            ok = (not payload.get("error") and not result.get("isError") and env is not None
                  and env.get("availability") == "available" and not env.get("error")
                  and isinstance(env.get("data"), dict) and bool(env["data"]))
            return True, ok, env
    except (ValueError, TypeError, AttributeError):
        pass
    return False, False, None


def _sse_result(text: str) -> tuple[bool, bool]:
    transport, ok, _ = _decode(text)
    return transport, ok


async def _one(client, i: int, symbol: str, tool: str = "signals_technical") -> dict:
    args = ({"symbol": symbol, "peers": [symbol + str(k) for k in range(5)]}
            if tool == "peer_compare" else {"symbol": symbol, "interval": "1D"})
    t0 = time.perf_counter()
    try:
        resp = await client.post("/mcp", json={"jsonrpc": "2.0", "id": i,
            "method": "tools/call", "params": {"name": tool, "arguments": args}},
            headers={"Accept": "application/json, text/event-stream"})
        transport, ok, env = _decode(resp.text)
        transport = transport and resp.status_code == 200
        data = (env or {}).get("data") or {}
        shape_ok = (len(data.get("rows", [])) == 6 and
                    all("roe" in r and not r.get("error") for r in data["rows"])) \
            if tool == "peer_compare" else data.get("rsi14") is not None
        return {"transport_ok": transport, "ok": bool(transport and ok and shape_ok),
                "ms": (time.perf_counter() - t0) * 1000,
                "cached": bool((env or {}).get("provenance", {}).get("cached")),
                "availability": (env or {}).get("availability"), "symbol": symbol,
                "errors": ((env or {}).get("warnings", []) +
                           [r["error"] for r in data.get("rows", []) if r.get("error")])
                          if not (transport and ok and shape_ok) else []}
    except (httpx.HTTPError, ValueError):
        return {"transport_ok": False, "ok": False,
                "ms": (time.perf_counter() - t0) * 1000, "cached": False, "symbol": symbol}


async def _docker(action: str, container: str):
    proc = await asyncio.create_subprocess_exec("docker", action, container,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    if proc.returncode:
        raise RuntimeError(err.decode())
    return out.decode()


async def _check_disposable(container: str):
    info = json.loads(await _docker("inspect", container))[0]
    if info["Config"].get("Labels", {}).get("opentrading-bench") != "1":
        raise ValueError("redis-down requires a container labelled opentrading-bench=1")
    return info


async def run_scenario(base: str, conc: int, rounds: int = 0, mode: str = "warm", *,
                       warmup_seconds: float = 5, sample_seconds: float = 15,
                       latency_ms: float = 20, redis_container: str | None = None) -> dict:
    if mode not in MODES or conc < 1 or sample_seconds <= 0 or warmup_seconds < 0:
        raise ValueError("invalid scenario parameters")
    if mode == "redis-down":
        if not redis_container:
            raise ValueError("redis-down requires --redis-container")
        await _check_disposable(redis_container)
    namespace = uuid.uuid4().hex
    records, health = [], []
    tool = "peer_compare" if mode == "peer" else "signals_technical"
    configured_latency = 1000 if mode == "stall" else latency_ms
    async with httpx.AsyncClient(base_url=base, timeout=60, trust_env=False) as client:
        response = await client.post("/__bench/config", json={"latency_ms": configured_latency})
        response.raise_for_status()
        config = response.json()
        warm_symbol = f"W{namespace}"
        await _one(client, -1, warm_symbol, tool)  # seed shared warm identity
        w_end = time.perf_counter() + warmup_seconds
        while time.perf_counter() < w_end:
            await _one(client, -2, f"WU{uuid.uuid4().hex}", tool)
        before = (await client.get("/__bench/state")).json()
        if mode == "redis-down" and not before["redis_client_active"]:
            raise RuntimeError("Redis was not active before outage injection")
        done = asyncio.Event()
        started = asyncio.Event()
        outage = {}

        async def monitor_health():
            while not done.is_set():
                t = time.perf_counter()
                r = await client.get("/__bench/state")
                health.append({"ms": (time.perf_counter() - t) * 1000,
                               "ok": r.status_code == 200})
                try:
                    await asyncio.wait_for(done.wait(), 0.1)
                except TimeoutError:
                    pass

        async def outage_midflight():
            await started.wait()
            await asyncio.sleep(min(0.5, sample_seconds / 3))
            await _docker("stop", redis_container)
            outage["stopped_during_sample"] = True

        counter = 0
        stop_at = time.perf_counter() + sample_seconds
        async def worker(worker_id):
            nonlocal counter
            while time.perf_counter() < stop_at:
                i = counter
                counter += 1
                cold = mode in {"cold", "stall", "health-under-load", "redis-down", "peer"}
                cold = cold or (mode == "mixed" and i % 2 == 1)
                symbol = f"S{namespace}{i}" if cold else warm_symbol
                started.set()
                records.append(await _one(client, i, symbol, tool))
                if mode == "burst":
                    await asyncio.sleep(0.1)  # synchronized waves via the path below

        sample_start = time.perf_counter()
        monitor = asyncio.create_task(monitor_health()) if mode == "health-under-load" else None
        injection = asyncio.create_task(outage_midflight()) if mode == "redis-down" else None
        try:
            if mode == "burst":
                while time.perf_counter() < stop_at:
                    wave = await asyncio.gather(*(_one(client, counter+k, warm_symbol, tool)
                                                  for k in range(conc)))
                    counter += conc
                    records.extend(wave)
                    await asyncio.sleep(0.1)
            else:
                await asyncio.gather(*(worker(k) for k in range(conc)))
            if injection:
                await injection
            sample_elapsed = time.perf_counter() - sample_start
            after = (await client.get("/__bench/state")).json()
            outage["state_during_outage"] = after if mode == "redis-down" else None
        finally:
            done.set()
            if monitor:
                await monitor
            if injection and not injection.done():
                injection.cancel()
                await asyncio.gather(injection, return_exceptions=True)
            if mode == "redis-down":
                await _docker("start", redis_container)
            await client.post("/__bench/config", json={"latency_ms": latency_ms})
        recovery = await _one(client, counter+1, f"REC{namespace}", tool)
        recovered_state = (await client.get("/__bench/state")).json()
    lat = sorted(r["ms"] for r in records)
    def percentile(p):
        return round(lat[min(len(lat)-1, int(p * len(lat)))], 2) if lat else None
    successes = sum(r["ok"] for r in records)
    return {"mode": mode, "concurrency": conc, "namespace": namespace,
            "sample_seconds": sample_elapsed, "warmup_seconds": warmup_seconds,
            "measurement": "benchmark" if sample_seconds >= 15 else "smoke",
            "requests": len(records), "rps": round(len(records)/sample_elapsed, 2),
            "p50_ms": percentile(.5), "p95_ms": percentile(.95), "p99_ms": percentile(.99),
            "transport_failures": sum(not r["transport_ok"] for r in records),
            "envelope_errors": sum(r["transport_ok"] and not r["ok"] for r in records),
            "success_rate": round(100*successes/max(len(records), 1), 2),
            "cache_hits": sum(r["cached"] for r in records),
            "config": config, "before": before, "after": after,
            "recovery_ok": recovery["ok"], "recovered_state": recovered_state,
            "health_probes": health, "outage": outage if mode == "redis-down" else None,
            "raw_requests": records}


async def main_async(args):
    modes = args.scenarios.split(",")
    if set(modes) - MODES:
        raise ValueError(f"unsupported scenarios: {set(modes) - MODES}")
    rows = []
    for mode in modes:
        for conc in map(int, args.levels.split(",")):
            row = await run_scenario(f"http://127.0.0.1:{args.port}", conc, mode=mode,
                warmup_seconds=args.warmup_seconds, sample_seconds=args.sample_seconds,
                latency_ms=args.latency_ms, redis_container=args.redis_container)
            rows.append(row)
            print(json.dumps({k: v for k, v in row.items() if k != "raw_requests"}), flush=True)
    report = {"label": args.label, "rows": rows}
    if args.output:
        await asyncio.to_thread(Path(args.output).write_text, json.dumps(report, indent=2) + "\n")
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--label", default="unlabeled")
    ap.add_argument("--latency-ms", type=float, default=20)
    ap.add_argument("--scenarios", default="cold,warm,burst,mixed,stall,health-under-load,peer")
    ap.add_argument("--levels", default="1,8,32")
    ap.add_argument("--warmup-seconds", type=float, default=5)
    ap.add_argument("--sample-seconds", type=float, default=15)
    ap.add_argument("--redis-container")
    ap.add_argument("--output")
    args = ap.parse_args()
    report = asyncio.run(main_async(args))
    if any(r["success_rate"] != 100 or not r["recovery_ok"] for r in report["rows"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
