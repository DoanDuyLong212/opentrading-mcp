"""Intel preset: odds, geo, regime, compare, redteam, evidence bundle."""

from __future__ import annotations

import asyncio
import functools
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.providers import intel as intel_p
from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers import yfinance as yf_p
from opentrading_mcp.providers.errors import (
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


def register_intel_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def world_prediction_odds(
        query: str | None = None,
        limit: int = 20,
        status: str | None = None,
        tag: str | None = None,
    ) -> dict[str, Any]:
        """Prediction-market odds via jina proxy to Gamma, then direct. Use for Fed/macro odds.

        limit: max events. status/tag: keep events whose title or status
        fields contain these substrings (case-insensitive).
        """
        try:
            data = await _call("o", intel_p.prediction_odds, query, secs=60.0)
            events = data.get("events", []) if isinstance(data, dict) else []
            if status is not None or tag is not None:
                filters = [f.lower() for f in (status, tag) if f]
                kept = []
                for event in events:
                    if not isinstance(event, dict):
                        continue
                    haystacks = [str(event.get("title", "")).lower()] + [
                        str(event.get(k, "")).lower()
                        for k in ("status", "tag", "state", "closed", "active")
                        if k in event
                    ]
                    if all(any(f in hay for hay in haystacks) for f in filters):
                        kept.append(event)
                events = kept
            return make_envelope(
                {"source": data.get("source"), "events": events[: max(int(limit), 1)]},
                source="polymarket",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("world_prediction_odds", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def geo_intel(
        topic: str | None = None, limit: int = 20, days: int | None = None
    ) -> dict[str, Any]:
        """Geopolitical coverage via GDELT. Use when geopolitics threatens markets.

        limit: max articles. days: keep articles from the last N days
        (undated articles are kept).
        """
        try:
            data = await _call(
                "g", intel_p.gdelt_events, topic or "geopolitical conflict sanctions", secs=60.0
            )
            articles = data.get("articles", []) if isinstance(data, dict) else []
            if days is not None:
                from datetime import date, timedelta

                cutoff = (date.today() - timedelta(days=max(int(days), 0))).isoformat()
                dated = []
                for article in articles:
                    stamp = str(article.get("date", ""))[:10] if isinstance(article, dict) else ""
                    if not stamp or stamp >= cutoff:
                        dated.append(article)
                articles = dated
            return make_envelope(
                {"query": data.get("query"), "articles": articles[: max(int(limit), 1)]},
                source="gdelt",
            )
        except ProviderUnavailable:
            await asyncio.sleep(10)
            try:
                data = await _call(
                    "g", intel_p.gdelt_events, topic or "geopolitical conflict", secs=60.0
                )
                return make_envelope(data, source="gdelt")
            except (ProviderUnavailable, ProviderBadData) as exc:
                return _na("geo_intel", str(exc))
        except ProviderBadData as exc:
            return _na("geo_intel", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def assets_rotation() -> dict[str, Any]:
        """Cross-asset 1y momentum classes into RISK-ON/OFF. Use for allocation reads."""
        try:
            drivers = await _call("r", yf_p.regime_assets, secs=120.0)
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("assets_rotation", str(exc))
        spx = (drivers.get("^GSPC") or {}).get("chg_1y_pct")
        gold = (drivers.get("GC=F") or {}).get("chg_1y_pct")
        btc = (drivers.get("BTC-USD") or {}).get("chg_1y_pct")
        signals: list[str] = []
        if isinstance(spx, (int, float)) and spx > 10:
            signals.append("equities momentum up")
        if isinstance(gold, (int, float)) and isinstance(spx, (int, float)) and gold > spx:
            signals.append("gold outperforming equities (defensive)")
        if isinstance(btc, (int, float)) and btc < 0:
            signals.append("crypto negative (risk-off lean)")
        regime = "risk-on" if (spx or 0) > 10 and not signals else "neutral/mixed"
        return make_envelope(
            {"regime": regime, "signals": signals, "drivers": drivers},
            source="computed-yfinance",
        )

    @server.tool(annotations=READ_ONLY)
    async def compare_equities(
        symbols: list[str], metrics: list[str] | None = None
    ) -> dict[str, Any]:
        """Head-to-head overview rows and momentum. Use when picking tickers.

        metrics: keep only matching row keys (symbol column always kept).
        """
        wanted = {m.lower() for m in metrics} if metrics else None
        rows: list[dict[str, Any]] = []
        for symbol in symbols[:4]:
            try:
                overview = await _call("o", vn_p.equity_quote_batch, [symbol.upper()], secs=45.0)
                candles = await _call("c", vn_p.quote_history, symbol.upper(), 30, secs=60.0)
                closes = [c["c"] for c in candles if c["c"]]
                mom = (
                    round((closes[-1] - closes[-20]) / closes[-20] * 100, 2)
                    if len(closes) >= 20
                    else None
                )
                row: dict[str, Any] = {
                    "symbol": symbol.upper(),
                    "quote": overview[0] if overview else {},
                    "momentum_1m_pct": mom,
                }
                if wanted is not None:
                    row = {"symbol": row["symbol"]} | {
                        k: v for k, v in row.items() if k.lower() in wanted
                    }
                rows.append(row)
            except (ProviderUnavailable, ProviderBadData) as exc:
                rows.append({"symbol": symbol.upper(), "error": str(exc)})
        return make_envelope({"rows": rows}, source="vnstock")

    @server.tool(annotations=READ_ONLY)
    async def evidence_bundle(
        claim_ids: list[str], calc_ids: list[str] | None = None
    ) -> dict[str, Any]:
        """Lock weighted conclusion by evidence bundle. Use last for final verdict.

        claim_ids: claim ids to lock; calc_ids: supporting calculation ids
        (pass [] when none).
        """
        bundle = {
            "claims": claim_ids,
            "calc_ids": calc_ids or [],
            "locked": bool(claim_ids),
            "note": "bundle closes server-side; attach calc ids at synthesis",
        }
        return make_envelope(bundle, source="local")

    @server.tool(annotations=READ_ONLY)
    async def oracle_meta() -> dict[str, Any]:
        """Aggregator snapshot plus source health. Use for dashboard meta."""
        try:
            pins = await _call("p", yf_p.market_pins, secs=60.0)
        except (ProviderUnavailable, ProviderBadData):
            pins = {}
        return make_envelope(
            {"pins": pins, "health": "run source_status for upstream detail"},
            source="aggregator",
        )

    return [
        {"name": "world_prediction_odds"},
        {"name": "geo_intel"},
        {"name": "assets_rotation"},
        {"name": "compare_equities"},
        {"name": "evidence_bundle"},
        {"name": "oracle_meta"},
    ]
