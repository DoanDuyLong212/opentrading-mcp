"""`opentrading-mcp cycle-refresh`: seed or refresh every cycle table outside the request path.

Run where DATABASE_URL points at the target database (a scheduled job or a laptop). It never
runs by itself; the MCP refresh tools stay for small manual top-ups. Steps:
1. cycle_ohlcv for every tracked symbol, in batches (each symbol its own transaction);
2. cycle_* derived tables in one transaction;
3. VN assets and global assets (each refresh + recompute).
Exit code 1 when any step failed, with the failures printed.
"""

from __future__ import annotations

import asyncio
import functools
import json
import sys
from datetime import date
from typing import Any


async def run(batch: int = 12, only: str | None = None) -> dict[str, Any]:
    from opentrading_mcp.tools import cycle_db as db
    from opentrading_mcp.tools.asset_cycle import refresh_global_assets, refresh_vn_assets
    from opentrading_mcp.tools.cycle_stats import ALL_SYMBOLS, TOOL, _finalize_compute, _refresh_one
    from opentrading_mcp.tools.shared import RATE_LIMITED, run_blocking

    report: dict[str, Any] = {"failed": []}
    if only in (None, "cycle"):
        today = date.today().isoformat()
        done = 0
        for i in range(0, len(ALL_SYMBOLS), batch):
            for sym in ALL_SYMBOLS[i : i + batch]:
                for attempt in range(2):
                    try:
                        await run_blocking(
                            functools.partial(db.transactional, _refresh_one, sym, today),
                            TOOL,
                            timeout_secs=180.0,
                        )
                        done += 1
                        break
                    except Exception as exc:
                        # vnstock's community quota is 60 requests/minute: wait it out once.
                        if RATE_LIMITED in str(exc) and attempt == 0:
                            print("vnstock rate limit: waiting 65s", file=sys.stderr)
                            await asyncio.sleep(65)
                            continue
                        report["failed"].append({"symbol": sym, "error": str(exc)[:200]})
                        break
            print(f"cycle_ohlcv: {done}/{len(ALL_SYMBOLS)}", file=sys.stderr)
        report["cycle_symbols"] = done
        try:
            report["cycle_finalize"] = await run_blocking(
                functools.partial(db.transactional, _finalize_compute, []), TOOL, timeout_secs=900.0
            )
        except Exception as exc:
            report["failed"].append({"step": "cycle_finalize", "error": str(exc)[:200]})
    for name, fn in (("vn_assets", refresh_vn_assets), ("global_assets", refresh_global_assets)):
        if only not in (None, name.split("_")[0]):
            continue
        try:
            report[name] = await fn()
        except Exception as exc:
            report["failed"].append({"step": name, "error": str(exc)[:200]})
    return report


def main(batch: int = 12, only: str | None = None) -> int:
    report = asyncio.run(run(batch, only))
    print(json.dumps(report, ensure_ascii=False, default=str, indent=1)[:20000])
    return 1 if report["failed"] else 0
