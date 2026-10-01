"""Scan preset: screener, breadth, rotation, alerts, flows, insider, technical."""

from __future__ import annotations

import asyncio
import functools
import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.providers import technicals as tech_p
from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import (
    ProviderAuthMissing,
    ProviderBadData,
    ProviderUnavailable,
)
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import READ_ONLY, AnyContext, run_blocking

ALERT_STATE_KEY = "mcp:scan:alert_state"
# Cross state must outlive a single scan cycle, otherwise cross_up/cross_down
# lose their prev value and re-fire every call (or silently reset). One hour
# covers normal scheduler gaps; a fresh state only costs one seeded first
# observation.
ALERT_STATE_TTL = 3600


def register_scan_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def stock_screener(
        filters: dict[str, Any] | None = None,
        max_pe: float | None = None,
        min_roe: float | None = None,
        limit: int = 20,
        technical: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Screen universe by valuation and quality. Use when hunting candidates.

        filters: {field: [min, max]} ranges (None side unbounded) or plain
        strings for symbol/exchange equality; use signals_screener_columns
        to discover valid fields. max_pe/min_roe are shortcuts for the same.
        technical: optional stage-3 timing filter on post-filter candidates
        ({rsi_lt, rsi_gt, above_sma20: true, below_sma20: true}).
        """
        from opentrading_mcp.providers import screener as sc_p
        from opentrading_mcp.providers import technicals as tech_p

        eff: dict[str, Any] = dict(filters or {})
        if max_pe is not None and "pe" not in eff:
            eff["pe"] = [None, max_pe]
        if min_roe is not None and "roe" not in eff:
            eff["roe"] = [min_roe, None]
        try:
            rows = await run_blocking(vn_p.listing_symbols, "stock_screener")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "stock_screener"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        warnings: list[str] = []
        # Bounded enrich: full width (≤30) only when a valuation filter needs
        # fundamentals; otherwise cap at 10 for display. Concurrent via
        # asyncio.gather + semaphore(5), 10s per symbol (run_blocking timeout).
        needs_valuation = any(k in eff for k in ("pe", "roe", "market_cap"))
        if needs_valuation:
            enrich_n = min(len(rows), max(max(limit, 1) * 2, 20), 30)
        else:
            enrich_n = min(len(rows), 10)
        enriched = 0
        sem = asyncio.Semaphore(5)

        async def _enrich_one(entry: dict[str, Any]) -> bool:
            sym = str(entry.get("symbol", "")).upper()
            if not sym:
                return False
            async with sem:
                try:
                    info = await run_blocking(
                        functools.partial(vn_p.equity_fundamentals, sym),
                        "stock_screener",
                        timeout_secs=10.0,
                    )
                except Exception:
                    return False
            if isinstance(info, dict):
                hit = False
                for key in ("pe", "roe", "market_cap"):
                    if info.get(key) is not None:
                        entry[key] = info[key]
                        hit = True
                return hit
            return False

        if enrich_n:
            results = await asyncio.gather(*(_enrich_one(entry) for entry in rows[:enrich_n]))
            enriched = sum(1 for r in results if r)
        if rows and enrich_n and enriched < enrich_n:
            warnings.append(f"fundamentals best-effort: {enriched}/{enrich_n} enriched")
        try:
            candidates = sc_p.apply_filters(rows, eff)
        except Exception as exc:
            return make_envelope(
                {"tool": "stock_screener"},
                source="unavailable",
                warnings=[f"filter error: {exc}"],
                availability="unavailable",
            )
        if technical is not None:
            allowed = {"rsi_lt", "rsi_gt", "above_sma20", "below_sma20"}
            unknown = [k for k in technical if k not in allowed]
            if unknown:
                return make_envelope(
                    {"tool": "stock_screener"},
                    source="unavailable",
                    warnings=[f"unknown technical rules: {unknown}"],
                    availability="unavailable",
                )
            shortlisted = candidates[: max(limit, 1)]

            async def _tech_ok(entry: dict[str, Any]) -> bool:
                sym = str(entry.get("symbol", "")).upper()
                if not sym:
                    return False
                try:
                    candles = await run_blocking(
                        functools.partial(vn_p.quote_history, sym, 80),
                        "stock_screener",
                        timeout_secs=10.0,
                    )
                    out = tech_p.compute(candles)
                except Exception:
                    return False
                try:
                    if "rsi_lt" in technical and not (out["rsi14"] < float(technical["rsi_lt"])):
                        return False
                    if "rsi_gt" in technical and not (out["rsi14"] > float(technical["rsi_gt"])):
                        return False
                    if technical.get("above_sma20") and not (
                        out["sma20"] is not None and out["last"] > out["sma20"]
                    ):
                        return False
                    if technical.get("below_sma20") and not (
                        out["sma20"] is not None and out["last"] < out["sma20"]
                    ):
                        return False
                except (TypeError, ValueError):
                    return False
                return True

            kept = await asyncio.gather(*(_tech_ok(e) for e in shortlisted))
            candidates = [e for e, ok in zip(shortlisted, kept, strict=True) if ok]
        return make_envelope(
            {
                "universe": len(rows),
                "filters": eff,
                "candidates": candidates[: max(limit, 1)],
            },
            source="vnstock",
            warnings=warnings,
        )

    @server.tool(annotations=READ_ONLY)
    async def signals_screener_columns(
        group: str | None = None, search: str | None = None
    ) -> dict[str, Any]:
        """Screener column catalog (valuation/quality/universe/price). Use to build filters.

        group: keep only that column group; search: keep columns whose
        key or label contains this substring (case-insensitive).
        """
        from opentrading_mcp.providers import screener as sc_p

        cols = sc_p.screener_columns(group=group, search=search)
        if not cols:
            return make_envelope(
                {"count": 0, "group": group, "search": search, "columns": {}},
                source="local",
                availability="empty",
            )
        return make_envelope(
            {"count": len(cols), "group": group, "search": search, "columns": cols},
            source="local",
        )

    @server.tool(annotations=READ_ONLY)
    async def signals_technical(
        symbol: str,
        interval: str = "1D",
        indicators: list[str] | None = None,
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Full technicals rating from local candles (daily only). Use for timing entries.

        indicators: keep only named outputs (e.g. rsi14, macd, sma20, recommend,
        patterns, support, resistance, rs_vs_bench, pos_52w, sma150);
        omit for the full set. interval other
        than '1D' is accepted but ignored.
        """
        from opentrading_mcp.providers import technicals as tech_p

        if ctx is not None:
            await ctx.log("info", f"signals_technical {symbol} {interval}")
        warnings_list: list[str] = []
        if interval != "1D":
            # Daily-only compute; other intervals are not resampled.
            warnings_list.append(
                f"daily-only: interval {interval!r} ignored, returning 1D daily data"
            )
        try:
            candles = await run_blocking(
                functools.partial(vn_p.quote_history, symbol, 250),
                "signals_technical",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "signals_technical"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        if not isinstance(candles, list) or len(candles) < 30:
            return make_envelope(
                {
                    "symbol": symbol.upper(),
                    "interval": "1D",
                    "note": "insufficient history",
                    "n": len(candles) if isinstance(candles, list) else 0,
                },
                source="vnstock",
                warnings=warnings_list,
                availability="empty",
            )
        try:
            bench_candles = await run_blocking(
                functools.partial(vn_p.quote_history, "VNINDEX", 250),
                "signals_technical",
            )
            bench = [c["c"] for c in bench_candles if c.get("c")]
        except (ProviderUnavailable, ProviderBadData) as exc:
            bench = []
            warnings_list.append(f"VNINDEX benchmark unavailable: {exc}")
        try:
            out = tech_p.compute(candles, benchmark=bench or None)
        except Exception as exc:
            return make_envelope(
                {"tool": "signals_technical"},
                source="unavailable",
                warnings=[f"technicals compute failed: {exc}"],
                availability="unavailable",
            )
        if indicators is not None:
            wanted = {i.lower() for i in indicators}
            out = {k: v for k, v in out.items() if str(k).lower() in wanted}
        return make_envelope(
            {"symbol": symbol.upper(), "interval": "1D", **out},
            source="computed-local",
            warnings=warnings_list,
        )

    @server.tool(annotations=READ_ONLY)
    async def sector_performance(level: int = 1, top_n: int = 50) -> dict[str, Any]:
        """GICS heatmap rows. Use for sector rotation reads.

        level: GICS tree depth. top_n: rows returned.
        """
        try:
            from opentrading_mcp.providers import vietstock as vs_p

            heatmap = await run_blocking(
                vs_p.industry_heatmap, "sector_performance", timeout_secs=45.0
            )
            rows = heatmap if isinstance(heatmap, list) else heatmap.get("data", [])
            filtered = [
                r
                for r in rows
                if isinstance(r, dict) and int(r.get("Level", level) or level) == level
            ] or rows
            return make_envelope(
                {"level": level, "rows": filtered[: max(int(top_n), 1)]}, source="vietstock"
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "sector_performance"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )

    @server.tool(annotations=READ_ONLY)
    async def money_flow(symbols: list[str] | None = None) -> dict[str, Any]:
        """Compose foreign flow: DNSE WS then Vietstock cross-check. Use for smart money.

        symbols: WS channels to read (default ["VNINDEX"]); falls back to
        Vietstock NN chart when cache is cold. Pair with block_trades for
        per-symbol negotiated put-through prints (different granularity).
        """
        try:
            from opentrading_mcp.providers import dnse as dnse_mod

            ws = dnse_mod.ws_snapshot(symbols or ["VNINDEX"])
            return make_envelope({"primary": "dnse-ws", "snapshot": ws}, source="dnse-ws")
        except ProviderUnavailable:
            pass
        try:
            from opentrading_mcp.providers import vietstock as vs_mod

            data = await run_blocking(
                vs_mod.nn_flow_chart,
                "money_flow",
                timeout_secs=45.0,
            )
            return make_envelope({"primary": "vietstock", "flow": data}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "money_flow"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )

    @server.tool(annotations=READ_ONLY)
    async def alert_check(rules: list[dict[str, Any]]) -> dict[str, Any]:
        """Evaluate price/RSI rules against live quotes. Use for live watch.

        Each rule: {symbol, threshold, metric ('price'|'rsi14'), op ('>'|'gt'|'>='|'gte'|
        '<'|'lt'|'<='|'lte'|'cross_up'|'cross_down')}.
        """
        wanted: dict[str, dict[str, Any]] = {}
        for entry in rules:
            if (
                isinstance(entry, dict)
                and entry.get("symbol")
                and entry.get("threshold") is not None
            ):
                wanted[str(entry["symbol"]).upper()] = entry
        if not wanted:
            return make_envelope(
                {"rules": len(rules), "triggered": [], "note": "rules need symbol+threshold"},
                source="local",
                availability="empty",
            )
        needs_history = any(
            str(e.get("metric", "price")) == "rsi14" for e in wanted.values()
        ) or any(str(e.get("op", ">")) in ("cross_up", "cross_down") for e in wanted.values())
        try:
            quotes = await run_blocking(
                functools.partial(vn_p.equity_quote_batch, list(wanted)),
                "alert_check",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "alert_check"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        # rsi14 metric needs candle history; cross ops need previous values
        history: dict[str, list[dict[str, Any]]] = {}
        prev_state: dict[str, Any] = {}
        warnings_list: list[str] = []
        if needs_history:
            from opentrading_mcp.providers import store as st_p

            raw_state = st_p.cache_get(ALERT_STATE_KEY)
            if isinstance(raw_state, (str, bytes)):
                try:
                    prev_state = json.loads(raw_state)
                except Exception as exc:
                    warnings_list.append(f"alert state unreadable, reset: {exc}")
                    prev_state = {}
            elif isinstance(raw_state, dict):
                prev_state = raw_state
            symbol_list = sorted(
                {str(q.get("symbol", "")).upper() for q in quotes if q.get("symbol")}
            )
            results = await asyncio.gather(
                *(
                    run_blocking(
                        functools.partial(vn_p.quote_history, sym, 30),
                        "alert_check_rsi",
                        timeout_secs=20.0,
                    )
                    for sym in symbol_list
                ),
                return_exceptions=True,
            )
            for sym, res in zip(symbol_list, results, strict=True):
                if isinstance(res, BaseException):
                    warnings_list.append(f"{sym}: history fetch failed: {res}")
                elif isinstance(res, list) and res:
                    history[sym] = res

        triggered: list[dict[str, Any]] = []
        for quote in quotes:
            symbol = str(quote.get("symbol", "")).upper()
            rule: dict[str, Any] | None = wanted.get(symbol)
            if rule is None:
                continue
            metric = str(rule.get("metric", "price"))
            if metric == "rsi14":
                candles = history.get(symbol)
                if not candles:
                    warnings_list.append(f"{symbol}: no history for rsi14")
                    continue
                try:
                    out = tech_p.compute(candles)
                    value = float(out["rsi14"])
                except Exception as exc:
                    warnings_list.append(f"{symbol}: rsi14 compute failed: {exc}")
                    continue
            else:
                price = quote.get("close_price") or quote.get("close") or 0
                try:
                    value = float(price)
                except (TypeError, ValueError):
                    continue
            try:
                threshold = float(rule["threshold"])
            except (TypeError, ValueError):
                continue
            op = str(rule.get("op", ">"))
            state_key = f"{symbol}:{metric}"
            if op.startswith("cross"):
                prev = prev_state.get(state_key)
                if prev is None:
                    # first observation: standing beyond threshold fires and seeds
                    hit = value > threshold if op == "cross_up" else value < threshold
                    if hit:
                        warnings_list.append(f"{symbol}: first state seeded for {op}")
                else:
                    try:
                        prev_f = float(prev)
                    except (TypeError, ValueError):
                        continue
                    if op == "cross_up":
                        hit = prev_f <= threshold and value > threshold
                    else:
                        hit = prev_f >= threshold and value < threshold
                prev_state[state_key] = value
            elif op in (">", "gt"):
                hit = value > threshold
            elif op in (">=", "gte"):
                hit = value >= threshold
            elif op in ("<", "lt"):
                hit = value < threshold
            elif op in ("<=", "lte"):
                hit = value <= threshold
            else:
                hit = value < threshold
            if hit:
                triggered.append(
                    {
                        "symbol": symbol,
                        "metric": metric,
                        "price": value,
                        "op": op,
                        "threshold": threshold,
                    }
                )
        if needs_history and prev_state:
            st_p.cache_set(ALERT_STATE_KEY, prev_state, ttl_seconds=ALERT_STATE_TTL)
        return make_envelope(
            {"rules": len(rules), "evaluated": len(quotes), "triggered": triggered},
            source="computed-local",
            warnings=warnings_list,
        )

    return [
        {"name": "stock_screener"},
        {"name": "signals_screener_columns"},
        {"name": "signals_technical"},
        {"name": "sector_performance"},
        {"name": "money_flow"},
        {"name": "alert_check"},
    ]
