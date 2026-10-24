"""Read-only offline reproductions; run with reviewed snapshot's src on PYTHONPATH."""
import asyncio
import copy
import json

import pandas as pd
from mcp.server.fastmcp import FastMCP

from opentrading_mcp.tools import compute_financial as cf
from opentrading_mcp.tools.cycle_stats import _major_troughs
from opentrading_mcp.tools.market_timing import _follow_through


def statement(periods, lines):
    return {
        "periods": periods,
        "rows": [{"norm_id": cf._FD_LINES[k][0][0], "values": v} for k, v in lines.items()],
    }


async def main():
    periods = ["Q1/2026", "Q2/2026"]
    data = {
        "KQKD": statement(periods, {
            "revenue": [100, 110], "gross": [40, 42], "net_income": [10, 12],
            "selling": [5, 6], "admin": [3, 4],
        }),
        "CDKT": statement(periods, {
            "assets": [100, 120], "current_assets": [50, 55],
            "current_liabilities": [20, 25], "cash": [10, 12],
            "liabilities": [40, 45], "equity": [60, 75], "receivables": [15, 18],
        }),
        "LCTT": statement(periods, {"cfo": [8, 11]}),
    }

    async def fake_call(tool, fn, *args, **kwargs):
        return copy.deepcopy(data[args[1]])

    async def no_cache(*args, **kwargs):
        return None

    async def capture(tool, fp, ttl, out, **kwargs):
        return out

    cf._call, cf.cache_lookup, cf.cache_store = fake_call, no_cache, capture
    server = FastMCP("offline-review")
    cf.register_compute_financial_tools(server)
    fn = server._tool_manager.get_tool("stock_forensic").fn
    baseline = await fn("SYNTHETIC", detail=True)
    data["CDKT"]["periods"] = ["Q3/2025", "Q4/2025"]
    shifted = await fn("SYNTHETIC", detail=True)
    ppe_previous, ppe_current = 30, 35
    canonical_aqi = (1 - (55 + ppe_current) / 120) / (1 - (50 + ppe_previous) / 100)
    dates = [f"2026-10-{i+1:02}" for i in range(6)]
    undercut = _follow_through(
        [110, 105, 100, 101, 102, 103], [100] * 6,
        [109, 104, 99, 98, 100, 101], dates,
    )
    intraday_break = _follow_through(
        [110, 105, 100, 101, 102, 103], [100] * 6,
        [109, 104, 99, 100, 98, 101], dates,
    )
    recovery = pd.Series([100, 80, 97], index=pd.date_range("2026-01-01", periods=3))
    output = {
        "aqi": {"actual": baseline["aqi"], "formula_with_ppe_30_35": canonical_aqi},
        "lvgi": {"actual": baseline["lvgi"], "ltd_plus_cl_over_assets_with_ltd_20_each_year": (45/120)/(40/100)},
        "period_alignment": {"output_unchanged_after_cdkt_shifted_two_quarters": baseline == shifted},
        "missing_depi": {"m_score_still_number": baseline["m_score"], "m_partial": baseline["m_partial"]},
        "up_day_new_low": undercut,
        "intraday_break_closes_above_old_low": intraday_break,
        "rebound_21_25pct_below_old_peak": {"events": [str(d) for d in _major_troughs(recovery)]},
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
