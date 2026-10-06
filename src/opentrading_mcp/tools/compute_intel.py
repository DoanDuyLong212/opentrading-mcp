"""Compute intel tools: FRED, WorldBank, sentiment, events, assets."""

from __future__ import annotations

import asyncio
import functools
import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.providers import intel as intel_p
from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers import yfinance as yf_p
from opentrading_mcp.providers.errors import (
    ProviderAuthMissing,
    ProviderBadData,
    ProviderUnavailable,
)
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import READ_ONLY, run_blocking


def _na(tool: str, reason: str) -> dict[str, Any]:
    return make_envelope(
        {"tool": tool}, source="unavailable", warnings=[reason], availability="unavailable"
    )


async def _call(tool: str, fn: Any, *args: Any, secs: float = 45.0) -> Any:
    return await run_blocking(functools.partial(fn, *args), tool, timeout_secs=secs)


def _find_numbers(payload: Any, *needles: str, limit: int = 12) -> list[float]:
    found: list[float] = []

    def walk(node: Any) -> None:
        if len(found) >= limit:
            return
        if isinstance(node, dict):
            for key, value in node.items():
                key_low = str(key).lower()
                if any(n in key_low for n in needles) and isinstance(value, (int, float)):
                    found.append(float(value))
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return found


def _read_runs() -> list[dict[str, Any]] | None:
    path = os.environ.get("MCP_RUNS_FILE", "data/runs.jsonl")
    if not os.path.exists(path):
        return None
    rows: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _fd_series(detail: dict[str, Any], include: str, exclude: str = "") -> list[float]:
    """Sum values of detail rows whose name matches include (and no exclude)."""
    if not isinstance(detail, dict):
        return []
    series: list[float] | None = None
    for row in detail.get("rows") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").lower()
        if include not in name or (exclude and exclude in name):
            continue
        values = [
            float(v) if isinstance(v, (int, float)) else 0.0 for v in (row.get("values") or [])
        ]
        if not any(values):
            continue
        if series is None:
            series = values
        else:
            series = [a + b for a, b in zip(series, values, strict=False)]
    return series or []


def _fd_pick(detail: dict[str, Any], *priority: tuple[str, str]) -> list[float]:
    """First matching (include, exclude) pair that yields a series."""
    for include, exclude in priority:
        got = _fd_series(detail, include, exclude)
        if got:
            return got
    return []


def _fd_first(detail: dict[str, Any], *needles: str) -> list[float]:
    for needle in needles:
        got = _fd_series(detail, needle)
        if got:
            return got
    return []


def register_compute_intel_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def fred_series(series_id: str, limit: int = 60, spark: bool = False) -> dict[str, Any]:
        """FRED observations. Use for US macro context.

        series_id like 'DGS10'; spark adds a value-only sparkline list.
        """
        try:
            data = await _call("f", intel_p.fred_series, series_id, limit)
            if spark and isinstance(data, dict):
                points = data.get("points", [])
                data["spark"] = [p.get("v") for p in points if isinstance(p, dict)]
            return make_envelope(data, source="fred")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("fred_series", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def world_macro_country(iso3: str, indicator: str, limit: int = 60) -> dict[str, Any]:
        """WorldBank series per country. Use for global GDP/CPI/debt context.

        iso3: 3-letter country code (VNM/USA); indicator like 'NY.GDP.MKTP.KD.ZG'.
        limit caps returned points.
        """
        try:
            data = await _call("w", intel_p.worldbank_country, iso3, indicator)
            if isinstance(data, dict) and isinstance(data.get("points"), list):
                data["points"] = data["points"][: max(int(limit), 1)]
            return make_envelope(data, source="worldbank")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("world_macro_country", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def world_fear_greed(limit: int = 7) -> dict[str, Any]:
        """Crypto fear/greed index. Use for risk-appetite reads.

        limit: number of recent daily readings returned.
        """
        try:
            data = await _call("f", intel_p.fear_greed)
            if isinstance(data, dict) and isinstance(data.get("series"), list):
                data["series"] = data["series"][: max(int(limit), 1)]
            return make_envelope(data, source="alternative.me")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("world_fear_greed", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def sentiment_score(symbol: str, limit: int = 20) -> dict[str, Any]:
        """Crowd sentiment from Fireant posts, Groq-scored. Use for hype risk.

        limit: max posts scored; without Groq key falls back to likes heuristic.
        """
        try:
            posts = await _call("s", intel_p.fireant_posts, symbol, max(int(limit), 1), secs=45.0)
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("sentiment_score", str(exc))
        if not posts:
            return make_envelope(
                {"symbol": symbol.upper(), "score": None}, source="fireant", availability="empty"
            )
        try:
            verdict = await _call(
                "g",
                intel_p.groq_chat,
                'Score crowd sentiment -1..1 as JSON {"score": x}.',
                str([p.get("text", "")[:200] for p in posts[:10]]),
                secs=45.0,
            )
            return make_envelope(
                {"symbol": symbol.upper(), "posts": len(posts), "llm": verdict[:500]},
                source="fireant+groq",
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData):
            likes = sum(int(p.get("likes", 0) or 0) for p in posts)
            score = max(-1.0, min(1.0, (likes / max(len(posts), 1) - 5) / 20))
            return make_envelope(
                {"symbol": symbol.upper(), "posts": len(posts), "score_heuristic": round(score, 2)},
                source="fireant",
                warnings=["groq unavailable, heuristic fallback"],
            )

    @server.tool(annotations=READ_ONLY)
    async def event_stats(query: str = "stock market", limit: int = 20) -> dict[str, Any]:
        """GDELT event counts for a query. Use for base-rate checks.

        limit: max articles fetched from GDELT.
        """
        try:
            data = await _call("e", intel_p.gdelt_events, query, max(int(limit), 1))
            return make_envelope(data, source="gdelt")
        except ProviderUnavailable:
            await asyncio.sleep(10)
            try:
                return make_envelope(await _call("e", intel_p.gdelt_events, query), source="gdelt")
            except (ProviderUnavailable, ProviderBadData) as exc:
                return _na("event_stats", str(exc))
        except ProviderBadData as exc:
            return _na("event_stats", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def compare_assets(assets: list[str], timeframe: str = "1d") -> dict[str, Any]:
        """Cross-asset last prices via yfinance. Use for allocation reads.

        assets: yfinance tickers (max 10). timeframe: '1d' (2d/1d),
        '1wk' (3mo/1wk), '1mo' (1y/1d) download window.
        """
        windows = {"1d": ("2d", "1d"), "1wk": ("3mo", "1wk"), "1mo": ("1y", "1d")}
        period, interval = windows.get(timeframe, ("2d", "1d"))
        try:
            return make_envelope(
                await _call("c", yf_p.batch_last, assets[:10], period, interval, secs=60.0),
                source="yfinance",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("compare_assets", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def insider_trading(symbol: str, limit: int = 10) -> dict[str, Any]:
        """Insider deals via vnstock Company. Use for informed-flow reads.

        limit: max deals returned.
        """
        try:
            rows = await _call("i", vn_p.insider_trading, symbol, limit)
            return make_envelope({"symbol": symbol.upper(), "deals": rows}, source="vnstock")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("insider_trading", str(exc))

    return [
        {"name": "fred_series"},
        {"name": "world_macro_country"},
        {"name": "world_fear_greed"},
        {"name": "sentiment_score"},
        {"name": "event_stats"},
        {"name": "compare_assets"},
        {"name": "insider_trading"},
    ]
