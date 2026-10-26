"""yfinance tools: global indices, commodities, yield curve, world breadth."""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.cache import TTL_SECONDS, cache_key
from opentrading_mcp.providers import yfinance as yf_p
from opentrading_mcp.providers.errors import (
    ProviderAuthMissing,
    ProviderBadData,
    ProviderUnavailable,
)
from opentrading_mcp.providers.store import acache_get
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import (
    READ_ONLY_OPEN,
    AnyContext,
    cache_lookup,
    cache_store,
    run_blocking,
)


def _na(tool: str, reason: str) -> dict[str, Any]:
    return make_envelope(
        {"tool": tool}, source="unavailable", warnings=[reason], availability="unavailable"
    )


def register_yf_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY_OPEN)
    async def yf_global_indices(
        tickers: list[str] | None = None,
        period: str = "2d",
        interval: str = "1d",
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """9 global benchmarks. Use for overnight context.

        tickers: subset override (default GLOBAL 9). period/interval: yfinance
        spellings ('2d', '1wk', '1mo'... x '1d'/'1wk').
        """
        if ctx is not None:
            await ctx.report_progress(0, 1, "fetch global")
        if tickers is None and period == "2d" and interval == "1d":
            # The 60s yf_loop keeps this exact board warm; custom args go live.
            hit = await acache_get(cache_key("yf_global_indices", "loop"))
            if hit is not None:
                import json

                cached = json.loads(hit)
                data = {k: v for k, v in cached.items() if k != "fetched_at"}
                return make_envelope(data, source="cache", data_time=cached.get("fetched_at"))
        else:
            custom = await cache_lookup(
                "yf_global_indices", f"{tickers}|{period}|{interval}"
            )
            if custom is not None:
                return custom
        try:
            data = await run_blocking(
                functools.partial(yf_p.batch_last, tickers or yf_p.GLOBAL_9, period, interval),
                "yf_global_indices",
                timeout_secs=50.0,
            )
            return await cache_store(
                "yf_global_indices", f"{tickers}|{period}|{interval}",
                TTL_SECONDS["world"], {"indices": data}, source="yfinance",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("yf_global_indices", str(exc))

    @server.tool(annotations=READ_ONLY_OPEN)
    async def yf_commodities(
        tickers: list[str] | None = None, period: str = "2d", interval: str = "1d"
    ) -> dict[str, Any]:
        """Gold, oil, metals, BTC, VND and dollar index. Use for input-cost context.

        tickers: subset override (default COMMO 13). period/interval: yfinance
        spellings.
        """
        if tickers is None and period == "2d" and interval == "1d":
            hit = await acache_get(cache_key("yf_commodities", "loop"))
            if hit is not None:
                import json

                cached = json.loads(hit)
                data = {k: v for k, v in cached.items() if k != "fetched_at"}
                return make_envelope(data, source="cache", data_time=cached.get("fetched_at"))
        else:
            custom = await cache_lookup(
                "yf_commodities", f"{tickers}|{period}|{interval}"
            )
            if custom is not None:
                return custom
        try:
            data = await run_blocking(
                functools.partial(yf_p.batch_last, tickers or yf_p.COMMO_13, period, interval),
                "yf_commodities",
                timeout_secs=50.0,
            )
            return await cache_store(
                "yf_commodities", f"{tickers}|{period}|{interval}",
                TTL_SECONDS["world"], {"items": data}, source="yfinance",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("yf_commodities", str(exc))

    @server.tool(annotations=READ_ONLY_OPEN)
    async def yf_yield_curve() -> dict[str, Any]:
        """US 2Y/10Y and inversion flag. Use for rates and regime context.

        Falls back to FRED DGS10/DGS2 when yfinance is blocked (datacenter IPs).
        """
        hit = await cache_lookup("yf_yield_curve", "-")
        if hit is not None:
            return hit
        try:
            data = await run_blocking(yf_p.yield_curve, "yf_yield_curve", timeout_secs=50.0)
            return await cache_store(
                "yf_yield_curve", "-", TTL_SECONDS["hour"],  # 2Y/10Y move intraday
                data, source="yfinance",
            )
        except (ProviderUnavailable, ProviderBadData):
            pass
        try:
            from opentrading_mcp.providers import intel as intel_p

            ten = await run_blocking(
                functools.partial(intel_p.fred_series, "DGS10", 5),
                "yf_yield_curve_fred", timeout_secs=30.0,
            )
            two = await run_blocking(
                functools.partial(intel_p.fred_series, "DGS2", 5),
                "yf_yield_curve_fred", timeout_secs=30.0,
            )
            # fred_series asks FRED for sort_order=desc: points[0] is the newest
            # observation (points[-1] was the oldest of the 5, about a week stale).
            ten_pts = ten.get("points") or []
            two_pts = two.get("points") or []
            if not ten_pts or not two_pts or not isinstance(ten_pts[0], dict) or not isinstance(two_pts[0], dict):
                raise ProviderBadData("FRED returned no DGS10/DGS2 observations")
            v10_raw, v2_raw = ten_pts[0].get("v"), two_pts[0].get("v")
            if v10_raw is None or v2_raw is None:
                # F10: a missing leg can never become a valid zero
                raise ProviderBadData("FRED newest observation missing value")
            us10y = float(v10_raw) / 100
            us2y = float(v2_raw) / 100
            d10, d2 = ten_pts[0].get("t"), two_pts[0].get("t")
            extra_warn = ["yfinance blocked — FRED DGS10/DGS2 fallback"]
            inverted: bool | None = us2y > us10y
            if d10 != d2:
                # F10 deep contract: legs dated differently are distinct
                # observations — both values are disclosed but the inversion
                # DECISION is withheld (never classified across incompatible
                # dates).
                inverted = None
                extra_warn.append(
                    f"FRED legs dated differently: 10Y {d10}, 2Y {d2} — inverted withheld"
                )
            return await cache_store(
                "yf_yield_curve", "-", TTL_SECONDS["hour"],
                {"us10y": us10y, "us2y": us2y, "inverted": inverted,
                 "as_of_10y": d10, "as_of_2y": d2},
                source="fred",
                warnings=extra_warn,
            )
        except (ProviderUnavailable, ProviderBadData, ProviderAuthMissing,
                TypeError, ValueError, IndexError) as exc:
            return _na("yf_yield_curve", f"yfinance + FRED both failed: {exc}")

    return [
        {"name": "yf_global_indices"},
        {"name": "yf_commodities"},
        {"name": "yf_yield_curve"},
    ]
