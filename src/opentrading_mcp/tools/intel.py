"""Intel: odds, geo, regime, compare, redteam, evidence bundle."""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.cache import TTL_SECONDS
from opentrading_mcp.providers import intel as intel_p
from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers import yfinance as yf_p
from opentrading_mcp.providers.errors import (
    ProviderBadData,
    ProviderUnavailable,
)
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import (
    READ_ONLY,
    READ_ONLY_OPEN,
    cache_lookup,
    cache_store,
    price_ttl,
    run_blocking,
)


def _na(tool: str, reason: str) -> dict[str, Any]:
    return make_envelope(
        {"tool": tool}, source="unavailable", warnings=[reason], availability="unavailable"
    )


async def _call(tool: str, fn: Any, *args: Any, secs: float = 45.0) -> Any:
    return await run_blocking(functools.partial(fn, *args), tool, timeout_secs=secs)


def register_intel_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY_OPEN)
    async def world_prediction_odds(
        query: str | None = None,
        limit: int = 20,
        tag: str | None = None,
    ) -> dict[str, Any]:
        """Polymarket odds via jina proxy to Gamma, then direct. Use for Fed/macro odds.

        query: substring in title/slug/description. tag: Polymarket tag
        (e.g. 'economics', 'fed', 'crypto'). Rows carry outcomes + prob_pct,
        sorted by 24h volume.
        """
        fp = f"{query}|{limit}|{tag}"
        hit = await cache_lookup("world_prediction_odds", fp)
        if hit is not None:
            return hit
        try:
            data = await _call("o", intel_p.prediction_odds, query, tag, limit, secs=60.0)
            events = data.get("events", []) if isinstance(data, dict) else []
            return await cache_store(
                "world_prediction_odds",
                fp,
                TTL_SECONDS["mins10"],
                {"source": data.get("source"), "events": events[: max(int(limit), 1)]},
                source="polymarket",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("world_prediction_odds", str(exc))

    @server.tool(annotations=READ_ONLY_OPEN)
    async def polymarket_event(
        slug: str,
    ) -> dict[str, Any]:
        """One Polymarket event detail by slug (every market + odds). Use to drill in.

        slug: from world_prediction_odds rows. Returns description, markets
        with outcome probs, volumes and end dates.
        """
        fp = f"{slug}"
        hit = await cache_lookup("polymarket_event", fp)
        if hit is not None:
            return hit
        try:
            data = await _call("e", intel_p.polymarket_event, slug, secs=60.0)
            return await cache_store(
                "polymarket_event", fp, TTL_SECONDS["mins10"],
                data, source="polymarket",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("polymarket_event", str(exc))

    @server.tool(annotations=READ_ONLY_OPEN)
    async def geo_intel(
        topic: str | None = None, limit: int = 20, days: int | None = None,
        military: bool = False,
    ) -> dict[str, Any]:
        """Geopolitical coverage via GDELT (politics-filtered) or military ADS-B flights.

        Default: political articles only (sports/noise dropped) + aggregate
        {top_sources, by_day, date_range}. military=true: live military flights from
        adsb.lol with nearest conflict-zone distance and signal-loss diff
        {count, by_country, by_type, near_zone, lost_near_zone} — use for
        military-activity reads around conflicts. limit: max articles. days: keep
        articles from the last N days (undated articles are kept).
        """
        fp = f"{topic}|{limit}|{days}|{military}"
        hit = await cache_lookup("geo_intel", fp)
        if hit is not None:
            return hit
        if military:
            from opentrading_mcp.providers import geo as geo_p

            try:
                flights = await _call("m", geo_p.military_flights, secs=30.0)
                track = geo_p.track_signal_loss(flights)
                by_country: dict[str, int] = {}
                by_type: dict[str, int] = {}
                for f in flights:
                    by_country[f.get("operator_country", "Unknown")] = (
                        by_country.get(f.get("operator_country", "Unknown"), 0) + 1
                    )
                    by_type[f.get("type", "mil-other")] = by_type.get(
                        f.get("type", "mil-other"), 0
                    ) + 1
                near = sorted(flights, key=lambda f: f.get("zone_km", 1e9))[:10]
                return await cache_store(
                    "geo_intel", fp, TTL_SECONDS["mins10"],
                    {
                        "count": len(flights),
                        "by_country": dict(
                            sorted(by_country.items(), key=lambda x: x[1], reverse=True)
                        ),
                        "by_type": by_type,
                        "near_zone": near,
                        **track,
                    },
                    source="adsb.lol",
                )
            except ProviderUnavailable as exc:
                return _na("geo_intel(military)", str(exc))
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
            from opentrading_mcp.providers import geo as geo_p

            political = geo_p.political_filter(articles)
            agg = geo_p.aggregate(political)
            dropped = len(articles) - len(political)
            warnings = [f"dropped {dropped} non-political articles"] if dropped else []
            if not political and articles:
                # filter-all is honest but useless — fall back to unfiltered top
                # with an explicit warning instead of an empty verdict
                political = articles
                agg = geo_p.aggregate(political)
                warnings = ["no political match — showing unfiltered top articles"]
            return await cache_store(
                "geo_intel", fp, TTL_SECONDS["mins10"],
                {
                    "query": data.get("query"),
                    **agg,
                    "articles": political[: max(int(limit), 1)],
                },
                source="gdelt",
                warnings=warnings or None,
            )
        except ProviderUnavailable as exc:
            return make_envelope(
                {"tool": "geo_intel"},
                source="unavailable",
                warnings=[f"{exc} (retry-after-gdelt)"],
                availability="unavailable",
            )
        except ProviderBadData as exc:
            return _na("geo_intel", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def assets_rotation() -> dict[str, Any]:
        """Cross-asset 1y momentum classes into RISK-ON/OFF. Use for allocation reads."""
        hit = await cache_lookup("assets_rotation", "-")
        if hit is not None:
            return hit
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
        risk_on = isinstance(spx, (int, float)) and spx > 10
        risk_off = any("risk-off" in s or "defensive" in s for s in signals)
        if risk_on and not risk_off:
            regime = "risk-on"
        elif risk_off:
            regime = "risk-off"
        else:
            regime = "neutral/mixed"
        return await cache_store(
            "assets_rotation", "-", TTL_SECONDS["documents"],
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
        fp = f"{symbols}|{metrics}"
        hit = await cache_lookup("compare_equities", fp)
        if hit is not None:
            return hit
        wanted = {m.lower() for m in metrics} if metrics else None
        rows: list[dict[str, Any]] = []
        warnings = (
            [f"capped 4 symbols, {len(symbols) - 4} dropped"] if len(symbols) > 4 else []
        )
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
        return await cache_store(
            "compare_equities", fp, price_ttl(),  # embeds live quotes + 1m momentum
            {"rows": rows}, source="vnstock", warnings=warnings or None,
        )

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
        hit = await cache_lookup("oracle_meta", "-")
        if hit is not None:
            return hit
        try:
            pins = await _call("p", yf_p.market_pins, secs=60.0)
        except (ProviderUnavailable, ProviderBadData):
            pins = {}
        return await cache_store(
            "oracle_meta", "-", TTL_SECONDS["world"],
            {"pins": pins, "health": "run source_status for upstream detail"},
            source="aggregator",
        )

    return [
        {"name": "world_prediction_odds"},
        {"name": "polymarket_event"},
        {"name": "geo_intel"},
        {"name": "assets_rotation"},
        {"name": "compare_equities"},
        {"name": "evidence_bundle"},
        {"name": "oracle_meta"},
    ]
