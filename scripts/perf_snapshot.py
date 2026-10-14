"""Perf snapshot: cold vs warm latency per tool over real stdio transport.

Run BEFORE and AFTER perf changes with the same set, then compare:
    uv run python scripts/perf_snapshot.py --label baseline --out perf/snapshot-baseline.json
    uv run python scripts/perf_snapshot.py --label final --out perf/snapshot-final.json

Each tool is called twice back-to-back in ONE server session: the 1st call is
cold (upstream fetch, unless the tool already caches), the 2nd shows the
server-side cache effect. A warmup call (source_status, excluded from results)
absorbs one-time import costs so cold numbers reflect per-tool fetch cost.

Output JSON is committed next to this script for before/after comparison.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import os
import statistics
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from opentrading_mcp.verify import VerifyClient  # noqa: E402
from opentrading_mcp.verify_matrix import _availability, extract_text  # noqa: E402

CALL_TIMEOUT = 75.0

# (tool, args) — light args to keep the snapshot fast; same set every run.
BENCH: list[tuple[str, dict]] = [
    ("market_snapshot", {}),
    ("market_movers", {"top_n": 3}),
    ("breadth_scan", {}),
    ("vn_quote_history", {"symbol": "VCB", "days": 5}),
    ("vn_equity_quote_batch", {"symbols": ["VCB"]}),
    ("signals_technical", {"symbol": "VCB", "indicators": ["rsi14"]}),
    ("valuation_run", {"symbol": "VCB"}),
    ("financial_ratios", {"symbol": "VCB"}),
    ("sbv_rates", {}),
    ("vs_categories", {}),
    ("distribution_count", {"symbol": "VNINDEX", "days": 30}),
    ("news_market", {"limit": 3}),
    ("vs_indicator_data", {"indicator": "CPI"}),
    ("economic_calendar", {"limit": 5}),
]


def payload_info(payload):
    """Extract availability/source/as_of/data_time from a tool payload."""
    info = {"availability": "?", "source": "?", "has_data_time": False}
    try:
        text = extract_text(payload)
        body = json.loads(text) if text else {}
    except (ValueError, TypeError):
        return info
    if not isinstance(body, dict):
        return info
    prov = body.get("provenance") or {}
    info["availability"] = body.get("availability", "?")
    info["source"] = prov.get("source", "?")
    info["has_data_time"] = bool(prov.get("data_time"))
    return info


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    client = VerifyClient(server_label="opentrading")
    command = [sys.executable, "-m", "opentrading_mcp", "serve"]
    calls = [("source_status", {}, CALL_TIMEOUT)]
    for name, tool_args in BENCH:
        calls.append((name, tool_args, CALL_TIMEOUT))  # cold
        calls.append((name, tool_args, CALL_TIMEOUT))  # warm
    results = await client.run(calls, "stdio", command)

    rows = []
    for (name, _, _), res in zip(calls, results):
        info = payload_info(res.payload) if res.ok else {"availability": "error", "source": "-", "has_data_time": False}
        rows.append({"tool": name, "ok": res.ok, "seconds": round(res.seconds, 2), **info})

    out_rows = []
    for i in range(0, len(BENCH)):
        cold, warm = rows[1 + 2 * i], rows[1 + 2 * i + 1]
        out_rows.append({"tool": cold["tool"], "cold": cold, "warm": warm})

    def med(key):
        vals = [r[key]["seconds"] for r in out_rows if r[key]["ok"]]
        return round(statistics.median(vals), 2) if vals else None

    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
    except OSError:
        commit = "unknown"

    snapshot = {
        "label": args.label,
        "date": datetime.date.today().isoformat(),
        "commit": commit,
        "redis_configured": bool(os.environ.get("REDIS_URL")),
        "call_timeout": CALL_TIMEOUT,
        "results": out_rows,
        "summary": {
            "n_tools": len(out_rows),
            "median_cold_s": med("cold"),
            "median_warm_s": med("warm"),
            "warm_faster": sum(1 for r in out_rows if r["warm"]["ok"] and r["cold"]["ok"] and r["warm"]["seconds"] < r["cold"]["seconds"]),
            "warm_from_cache": sum(1 for r in out_rows if r["warm"]["source"] == "cache"),
            "with_data_time": sum(1 for r in out_rows if r["cold"]["has_data_time"] or r["warm"]["has_data_time"]),
        },
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=1)
        f.write("\n")
    s = snapshot["summary"]
    print(f"[{args.label}] tools={s['n_tools']} median_cold={s['median_cold_s']}s "
          f"median_warm={s['median_warm_s']}s warm_faster={s['warm_faster']} "
          f"warm_from_cache={s['warm_from_cache']} with_data_time={s['with_data_time']} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
