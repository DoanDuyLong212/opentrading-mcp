"""Benchmark cold (no cache) vs warm (Redis-hit) for read tools.

Usage:
  .venv/bin/python scripts/bench_cold_warm.py --tools market_snapshot,money_flow --out perf/bench.jsonl
  .venv/bin/python scripts/bench_cold_warm.py --all-reads --out perf/bench.jsonl

For each tool: flush its mcp: keys (Redis + memory), call once (cold),
call again (warm). Writes/heavy tools are never called (see SKIP).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

CALL_TIMEOUT = 45.0
GAP_SECONDS = 0.7

SKIP = {
    # writes / state changes
    "alert_create", "alert_delete", "alert_pause", "alert_resume",
    "watchlist_add", "watchlist_create", "watchlist_delete", "watchlist_remove",
    "watchlist_update", "planned_targets",
    # heavy compute / full-market scans (minutes, hammer providers)
    "quant_backtest", "param_sweep", "event_study", "pattern_match",
    "signals_scan", "stock_screener", "doctor", "brief_build",
    "scenario_simulate", "portfolio_optimize", "valuation_run",
    "cycle_stats_refresh", "cycle_stats_finalize", "g_asset_refresh",
    "vn_asset_refresh",
    # needs arbitrary URL / interactive input
    "web_fetch",
    # debug / infra
    "dnse_ws_snapshot", "source_status", "oracle_meta",
}

SAMPLES = [  # (matcher, value) — first match wins, case-insensitive
    ("series", "DGS10"), ("run_id", "1"),
    ("symbol", "VCB"), ("ticker", "VCB"), ("code", "VCB"), ("stock", "VCB"),
    ("index", "VNINDEX"), ("indices", "VNINDEX"),
    ("market", "HOSE"), ("exchange", "HOSE"), ("floor", "HOSE"),
    ("query", "VCB"), ("keyword", "VCB"), ("keywords", "ngân hàng"),
    ("currency", "USD"), ("commodity", "gold"), ("coin", "BTC"),
    ("country", "Vietnam"), ("sector", "Ngân hàng"), ("industry", "bank"),
    ("limit", 5), ("count", 5), ("top", 5), ("page_size", 5), ("size", 5),
    ("page", 1), ("days", 30), ("period", 30), ("years", 1), ("window", 20),
    ("interval", "D"), ("timeframe", "D"), ("range", "1M"),
    ("id", 1), ("post_id", 1),
]


def sample_args(schema: dict, tool: str = "") -> dict | None:
    props = (schema or {}).get("properties", {}) or {}
    required = (schema or {}).get("required", []) or []
    args: dict = {}
    for name in required:
        spec = props.get(name, {}) or {}
        low = name.lower()
        if "enum" in spec and spec["enum"]:
            args[name] = spec["enum"][0]
            continue
        if spec.get("type") == "integer":
            args[name] = 5
            continue
        if spec.get("type") == "number":
            args[name] = 5
            continue
        if spec.get("type") == "boolean":
            args[name] = False
            continue
        if spec.get("type") == "array":
            if tool.startswith("crypto_"):
                args[name] = ["BTCUSDT", "ETHUSDT"]
            elif "asset" in low:
                args[name] = ["GC=F", "BTC-USD", "^GSPC"]
            elif "symbol" in low or "ticker" in low or "code" in low:
                args[name] = ["VCB", "HPG"]
            else:
                args[name] = []
            continue
        hit = next((v for m, v in SAMPLES if m in low), None)
        if hit is None:
            return None  # unknown required param — skip tool
        args[name] = hit
    return args


async def flush_tool(tool: str) -> None:
    prefix = f"mcp:{tool}:"
    from opentrading_mcp.providers import store as store_p

    for k in [k for k in store_p._memory if k.startswith(prefix)]:
        store_p._memory.pop(k, None)
    cli = store_p._redis()
    if cli is not None:
        try:
            keys = await asyncio.to_thread(cli.keys, prefix + "*")
            if keys:
                await asyncio.to_thread(cli.delete, *keys)
        except Exception:
            pass


async def call_tool(server: object, name: str, args: dict) -> tuple[bool, str]:
    try:
        res = await asyncio.wait_for(server.call_tool(name, args), CALL_TIMEOUT)
    except Exception as exc:  # timeout / validation / provider
        return False, f"{type(exc).__name__}: {str(exc)[:120]}"
    blocks = res[0] if isinstance(res, tuple) else (getattr(res, "content", []) or [])
    text = "".join(getattr(b, "text", "") for b in blocks)
    try:
        payload = json.loads(text) if text else {}
    except Exception:
        return False, "non-JSON result"
    if isinstance(payload, dict) and payload.get("availability") == "unavailable":
        w = payload.get("warnings") or []
        return False, f"unavailable: {str(w[0])[:100] if w else '?'}"
    if getattr(res, "isError", False):
        return False, text[:100]
    return True, ""


async def bench(server: object, name: str, args: dict) -> dict:
    await flush_tool(name)
    t0 = time.perf_counter()
    ok1, note1 = await call_tool(server, name, args)
    dt1 = time.perf_counter() - t0
    await asyncio.sleep(0.2)
    t0 = time.perf_counter()
    ok2, note2 = await call_tool(server, name, args)
    dt2 = time.perf_counter() - t0
    return {
        "tool": name, "args": args,
        "cold_s": round(dt1, 2), "cold_ok": ok1, "cold_note": note1,
        "warm_s": round(dt2, 2), "warm_ok": ok2, "warm_note": note2,
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tools", default="")
    ap.add_argument("--all-reads", action="store_true")
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()

    from dotenv import load_dotenv

    load_dotenv()

    # Bench harness calls tools outside a real MCP request: Context.log /
    # report_progress would raise "not available outside of a request".
    # Silence them — they carry no benchmark signal.
    from mcp.server.fastmcp.server import Context as _FastCtx

    async def _noop(self, *a: object, **k: object) -> None:
        return None

    _FastCtx.log = _noop  # type: ignore[method-assign]
    _FastCtx.report_progress = _noop  # type: ignore[method-assign]

    from opentrading_mcp.server import create_server, register_all

    server = create_server()
    register_all(server)
    listed = await server.list_tools()
    schemas = {t.name: (t.inputSchema or {}) for t in listed}

    if ns.all_reads:
        names = sorted(n for n in schemas if n not in SKIP)
    else:
        names = [n.strip() for n in ns.tools.split(",") if n.strip()]

    done: set[str] = set()
    if os.path.exists(ns.out):
        with open(ns.out) as fh:
            for line in fh:
                try:
                    done.add(json.loads(line)["tool"])
                except Exception:
                    pass

    with open(ns.out, "a") as fh:
        for i, name in enumerate(names):
            if name in done or name not in schemas:
                continue
            args = sample_args(schemas[name], name)
            if args is None:
                fh.write(json.dumps({"tool": name, "skipped": "unknown-required-param"}) + "\n")
                continue
            row = await bench(server, name, args)
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            flag = "OK " if row["cold_ok"] else "FAIL"
            print(f"[{i+1}/{len(names)}] {flag} {name}: cold={row['cold_s']}s warm={row['warm_s']}s {row['cold_note']}", flush=True)
            await asyncio.sleep(GAP_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
